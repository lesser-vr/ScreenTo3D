"""Full-reference RGB metrics; both eyes share independently defined GT masks."""
import cv2
import numpy as np


def rgb_metrics(actual,expected,mask):
    if actual.dtype!=np.uint8 or expected.dtype!=np.uint8 or actual.shape!=expected.shape or actual.ndim!=3 or actual.shape[2]!=3 or mask.shape!=actual.shape[:2]:
        raise ValueError('Invalid reference RGB geometry')
    n=int(mask.sum())
    if not n:return dict(pixels=0,mae=None,mse=None,psnr_db=None,ssim=None,perfect=False)
    x=actual.astype(np.float32);y=expected.astype(np.float32)
    delta=(x-y)[mask];mse=float(np.mean(delta.astype(np.float64)**2))
    # Wang-style 11x11 Gaussian SSIM, sigma 1.5, population covariance, RGB mean.
    blur=lambda v:cv2.GaussianBlur(v,(11,11),1.5,borderType=cv2.BORDER_REFLECT_101)
    ux,uy=blur(x),blur(y)
    vx=np.maximum(blur(x*x)-ux*ux,0);vy=np.maximum(blur(y*y)-uy*uy,0)
    cov=blur(x*y)-ux*uy;c1=(.01*255)**2;c2=(.03*255)**2
    score=((2*ux*uy+c1)*(2*cov+c2))/((ux*ux+uy*uy+c1)*(vx+vy+c2))
    return dict(pixels=n,mae=float(np.abs(delta).mean()),mse=mse,
        psnr_db=float(10*np.log10(255**2/mse)) if mse else None,ssim=float(score[mask].mean()),perfect=mse==0)


def half_tb_reference(eyes):
    result=[]
    for eye in eyes:
        if eye.shape[0]%2:raise ValueError('Even fixture height required')
        # Independent integer box reduction; same delivered sampling contract.
        result.append(((eye[::2].astype(np.uint16)+eye[1::2].astype(np.uint16)+1)//2).astype(np.uint8))
    return result


def restored_eyes(pixels,layout,width,height):
    if pixels.ndim!=3 or pixels.shape[2]!=4 or not np.all(pixels[:,:,3]==255):raise ValueError('Invalid native opaque pixels')
    if layout=='full-sbs':
        if pixels.shape[:2]!=(height,width*2):raise ValueError('Invalid Full SBS geometry')
        return [np.ascontiguousarray(x[:,:,:3]) for x in np.split(pixels,2,axis=1)]
    if layout!='half-tb' or pixels.shape[:2]!=(height,width):raise ValueError('Invalid Half TB geometry')
    return [cv2.resize(x[:,:,:3],(width,height),interpolation=cv2.INTER_LINEAR) for x in np.split(pixels,2,axis=0)]


def reference_eyes(eyes,layout):
    if layout=='full-sbs':return eyes
    if layout!='half-tb':raise ValueError('Unsupported reference packing')
    return [cv2.resize(x,(eyes[0].shape[1],eyes[0].shape[0]),interpolation=cv2.INTER_LINEAR) for x in half_tb_reference(eyes)]
