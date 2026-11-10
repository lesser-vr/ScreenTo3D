"""Known-truth disparity metrics with calibration independent of scored frames."""
import cv2
import numpy as np


def fit_affine(samples,targets):
    x=np.concatenate(samples).astype(np.float64);y=np.concatenate(targets).astype(np.float64)
    if x.shape!=y.shape or x.size<100 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Invalid calibration samples')
    centered=x-x.mean();variance=np.mean(centered**2)
    if variance<1e-12:raise ValueError('Flat prediction cannot calibrate disparity')
    scale=float(np.mean(centered*(y-y.mean()))/variance)
    if scale<=0:raise ValueError('Inverse depth polarity disagrees with ground truth')
    return dict(scale=scale,offset=float(y.mean()-scale*x.mean()),samples=x.size,
                truth_span_px=float(np.quantile(y,.95)-np.quantile(y,.05)),truth_mean_px=float(y.mean()))


def align(prediction,calibration):
    prediction=np.asarray(prediction,dtype=np.float32)
    if prediction.ndim!=2 or not np.isfinite(prediction).all():raise ValueError('Invalid prediction')
    return prediction*calibration['scale']+calibration['offset']


def truth_edges(truth):
    finite=np.isfinite(truth)&(truth>=0)
    safe=np.where(finite,truth,0)
    edges=np.zeros(truth.shape,bool)
    jump=np.abs(safe[:,1:]-safe[:,:-1])>1
    edges[:,1:]|=jump;edges[:,:-1]|=jump
    jump=np.abs(safe[1:]-safe[:-1])>1
    edges[1:]|=jump;edges[:-1]|=jump
    return (cv2.dilate(edges.astype(np.uint8),np.ones((3,3),np.uint8))>0)&finite


def error_metrics(error,mask):
    values=error[mask].astype(np.float64)
    if not np.isfinite(values).all():raise ValueError('Nonfinite measured error')
    if not values.size:return dict(pixels=0,mae_px=None,rmse_px=None,bad1_percent=None)
    return dict(pixels=values.size,mae_px=float(np.mean(np.abs(values))),
                rmse_px=float(np.sqrt(np.mean(values**2))),bad1_percent=float(np.mean(np.abs(values)>1)*100))


def spatial_error(prediction,truth):
    if prediction.shape!=truth.shape or not np.isfinite(prediction).all():raise ValueError('Invalid spatial prediction')
    valid=np.isfinite(truth)&(truth>=0)
    error=prediction-truth
    return dict(all=error_metrics(error,valid),edges=error_metrics(error,valid&truth_edges(truth)),
                valid_fraction=float(valid.mean()))


def temporal_geometry(truth,next_truth,target_truth,flow):
    """Forward transport, with a prediction-independent target-visibility check.

    Spring disp2 is target disparity on reference coordinates, not a disparity delta.
    All sampled GT values already use full-HD pixel units, despite UHD storage.
    """
    if truth.shape!=next_truth.shape or truth.shape!=target_truth.shape or flow.shape!=truth.shape+(2,):
        raise ValueError('Invalid temporal ground truth geometry')
    h,w=truth.shape;yy,xx=np.indices((h,w),dtype=np.float32)
    mx=xx+flow[:,:,0];my=yy+flow[:,:,1]
    finite=np.isfinite(truth)&np.isfinite(target_truth)&np.isfinite(flow).all(axis=2)&(truth>=0)&(target_truth>=0)
    mx=np.where(np.isfinite(mx),mx,-10).astype(np.float32)
    my=np.where(np.isfinite(my),my,-10).astype(np.float32)
    projected=cv2.remap(next_truth.astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=float('nan'))
    valid=finite&(mx>=1)&(my>=1)&(mx<w-2)&(my<h-2)
    valid &= np.isfinite(projected)&(np.abs(projected-target_truth)<=.5)
    valid=cv2.erode(valid.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
    return mx,my,valid,target_truth-truth,truth_edges(truth)


def temporal_error(previous,current,geometry):
    mx,my,valid,truth_delta,edges=geometry
    if previous.shape!=current.shape or previous.shape!=valid.shape or not np.isfinite(previous).all() or not np.isfinite(current).all():
        raise ValueError('Invalid temporal predictions')
    transported=cv2.remap(current.astype(np.float32),mx,my,cv2.INTER_LINEAR)
    error=transported-previous-truth_delta
    return dict(all=error_metrics(error,valid),edges=error_metrics(error,valid&edges),
                changing_depth=error_metrics(error,valid&(np.abs(truth_delta)>=.1)),
                valid_fraction=float(valid.mean()),frozen_control=error_metrics(-truth_delta,valid))
