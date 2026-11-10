"""CPU-only quality measurements; reference errors and natural proxies stay distinct."""
import cv2
import numpy as np


def finite_image(value, dimensions):
    value=np.asarray(value)
    if value.ndim!=dimensions or not np.isfinite(value).all():
        raise ValueError('Invalid quality measurement image')
    return value


def masked_error(actual, expected, mask):
    actual=finite_image(actual,3);expected=finite_image(expected,3)
    if actual.shape!=expected.shape or mask.shape!=actual.shape[:2]:
        raise ValueError('Quality image/mask geometry mismatch')
    count=int(np.count_nonzero(mask))
    if not count:return dict(pixels=0,mae=None,rmse=None)
    error=(actual.astype(np.float32)-expected.astype(np.float32))[mask]
    return dict(pixels=count,mae=float(np.abs(error).mean()),rmse=float(np.sqrt(np.mean(error**2))))


def motion_map(previous,current):
    """Independent RGB-only Farneback correspondence with FB/photometric masks."""
    if previous.shape!=current.shape or previous.ndim!=3:raise ValueError('Invalid flow frames')
    old=cv2.cvtColor(previous,cv2.COLOR_RGB2GRAY);new=cv2.cvtColor(current,cv2.COLOR_RGB2GRAY)
    forward=cv2.calcOpticalFlowFarneback(old,new,None,.5,3,15,3,5,1.2,0)
    backward=cv2.calcOpticalFlowFarneback(new,old,None,.5,3,15,3,5,1.2,0)
    yy,xx=np.indices(old.shape,dtype=np.float32)
    mx,my=xx+backward[:,:,0],yy+backward[:,:,1]
    warped_flow=cv2.remap(forward,mx,my,cv2.INTER_LINEAR)
    warped_gray=cv2.remap(old,mx,my,cv2.INTER_LINEAR)
    valid=(mx>=1)&(mx<old.shape[1]-2)&(my>=1)&(my<old.shape[0]-2)
    valid &= np.linalg.norm(backward+warped_flow,axis=2)<=1
    valid &= np.abs(new.astype(np.int16)-warped_gray.astype(np.int16))<=12
    valid=cv2.erode(valid.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
    edge=cv2.dilate(cv2.Canny(new,50,120),np.ones((3,3),np.uint8))!=0
    return mx,my,valid,edge


def temporal_disparity(previous,current,correspondence):
    previous=finite_image(previous,2);current=finite_image(current,2)
    mx,my,valid,edge=correspondence
    if previous.shape!=current.shape or current.shape!=valid.shape:raise ValueError('Invalid disparity geometry')
    warped=cv2.remap(previous.astype(np.float32),mx,my,cv2.INTER_LINEAR)
    delta=current-warped
    def measure(mask):
        values=delta[mask]
        return dict(pixels=values.size,rmse_px=float(np.sqrt(np.mean(values**2))) if values.size else None,
                    p95_abs_px=float(np.quantile(np.abs(values),.95)) if values.size else None)
    return dict(all=measure(valid),edges=measure(valid&edge),valid_fraction=float(valid.mean()),
                edge_valid_fraction=float((valid&edge).sum()/max(1,edge.sum())))


def edge_reprojection(rgb,eyes,disparity):
    """Visible-source edge preservation proxy, not a target-view/depth oracle.

    Independently forward-z-buffer each eye to exclude occluded source samples.
    Half-format eyes must already be restored to the input sampling grid.
    """
    rgb=finite_image(rgb,3);disparity=finite_image(disparity,2)
    h,w=disparity.shape
    if rgb.shape!=(h,w,3) or len(eyes)!=2:raise ValueError('Invalid stereo geometry')
    yy,xx=np.indices((h,w),dtype=np.float32)
    edges=cv2.dilate(cv2.Canny(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),50,120),np.ones((3,3),np.uint8))!=0
    rows=[]
    for eye,sign in zip(eyes,(1,-1)):
        if eye.shape!=rgb.shape:raise ValueError('Invalid eye shape')
        tx=xx+disparity*.5*sign
        nearest=np.rint(tx).astype(np.int32)
        inside=(nearest>=2)&(nearest<w-2)
        address=np.arange(h,dtype=np.int64)[:,None]*w+np.clip(nearest,0,w-1)
        front=np.full(h*w,-np.inf,np.float32)
        np.maximum.at(front,address[inside],disparity[inside])
        visible=inside&(disparity>=front[address]-.05)
        # Forward visibility is approximate near fractional coverage: exclude
        # its one-pixel rim instead of counting genuinely hidden colors as errors.
        visible=cv2.erode(visible.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
        mask=visible&edges
        reconstructed=cv2.remap(eye,tx,yy,cv2.INTER_LINEAR)
        row=masked_error(reconstructed,rgb,mask)
        row['edge_coverage']=float(mask.sum()/max(1,edges.sum()));rows.append(row)
    return rows


def step_response(values,initial,target,hz=60,hold=5):
    """Response at source times; first changed input is t=0, not display time."""
    values=np.asarray(values,dtype=float)
    if not np.isfinite(values).all() or not np.isfinite([initial,target,hz]).all() or hz<=0 or hold<1:
        raise ValueError('Invalid response samples')
    span=target-initial
    if abs(span)<.05:return dict(t90_ms=None,updates_to_90=None,gain=None,reason='insufficient_target_step')
    tolerance=abs(span)*.1
    reached=next((i for i in range(max(0,len(values)-hold+1))
                  if np.all(np.abs(values[i:]-target)<=tolerance)),None)
    crossing=np.flatnonzero((values-initial)/span>=.9)
    gain=float((np.mean(values[-min(8,len(values)):])-initial)/span) if len(values) else None
    return dict(t90_ms=reached*1000/hz if reached is not None else None,
                updates_to_90=reached+1 if reached is not None else None,gain=gain,
                first_90_ms=int(crossing[0])*1000/hz if crossing.size else None,
                overshoot_fraction=max(0.,float(np.max((values-initial)/span))-1.) if len(values) else None,
                reason=None if reached is not None else 'target_not_reached')


def unpack_half_tb(pixels,width,height):
    if pixels.ndim!=3 or pixels.shape[0]%2 or pixels.shape[2] not in (3,4):
        raise ValueError('Invalid Half TB image')
    half=pixels.shape[0]//2
    return [cv2.resize(eye[:,:,:3],(width,height),interpolation=cv2.INTER_AREA)
            for eye in (pixels[:half],pixels[half:])]
