"""Independent analytic three-camera RGB/depth oracle, no tested image warper."""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

SCENES=('room','thin_edges','dark_objects','depth_layers')
WIDTH,HEIGHT=1280,720
BASELINE=.03
CONVERGENCE_Z=4.5


def objects(scene,t):
    motion=.22*np.sin(t*2.4)
    common=[('back',(9.,),[158,178,194],0),('floor',(-1.,),[160,130,90],1)]
    if scene=='room':
        return common+[
            ('box',(-1.45,-.8,3.5, -.45,.2,4.3),[185,88,38],2),
            ('box',(.5,-1,5.2, 1.5,.4,6.1),[65,115,185],3),
            ('sphere',(.2+motion,-.35,2.9,.65),[195,55,45],4),
            ('sphere',(-.4,.6,5.8,.5),[230,220,170],5)]
    if scene=='thin_edges':
        bars=[('box',(x+motion,-1,3.0,x+motion+.018,.8,3.035),[44,70,95],10+i)
              for i,x in enumerate(np.linspace(-1.7,1.5,9))]
        return common+bars+[
            ('sphere',(.5,-.2,5.2,.65),[195,55,45],30),
            ('box',(-1.2,-1,6.4,-.3,.6,7.2),[65,145,95],31)]
    if scene=='dark_objects':
        common[0]=('back',(9.,),[12,16,24],0)
        common[1]=('floor',(-1.,),[34,42,50],1)
        return common+[
            ('sphere',(motion,-.1,2.7,.72),[205,165,72],2),
            ('sphere',(-1.,-.35,4.6,.6),[80,135,185],3),
            ('box',(.8,-1,5.5,1.4,.55,6.2),[100,65,135],4)]
    if scene=='depth_layers':
        return common+[
            ('box',(-1.6+motion,-1,2.5,-.95+motion,.8,2.8),[220,190,100],2),
            ('sphere',(.1,-.1,3.8,.7),[105,175,150],3),
            ('box',(.85,-1,5.,1.4,.65,5.3),[170,80,140],4),
            ('box',(-1.8,-1,7.,-.8,1,7.5),[80,130,210],5)]
    raise ValueError('Unknown analytic scene')


def render(scene,t,camera_x=0.,width=WIDTH,height=HEIGHT):
    """Parallel cameras, off-axis projection; ray t equals camera-axis Z."""
    focal=.9*width;yy,xx=np.indices((height,width),dtype=np.float32)
    rx=(xx+.5-width/2)/focal-camera_x/CONVERGENCE_Z
    ry=(height/2-yy-.5)/focal
    rays=(rx,ry,np.ones_like(rx));origin=(camera_x,0.,0.)
    depth=np.full(rx.shape,np.inf,np.float32);ids=np.full(rx.shape,-1,np.int16)
    normals=np.zeros((*rx.shape,3),np.float32);colors=np.zeros_like(normals)
    for kind,params,color,identifier in objects(scene,t):
        normal=np.zeros_like(normals)
        if kind in ('back','floor'):
            axis=2 if kind=='back' else 1
            with np.errstate(divide='ignore',invalid='ignore'):distance=(params[0]-origin[axis])/rays[axis]
            normal[:,:,axis]=-1 if kind=='back' else 1
            valid=np.isfinite(distance)&(distance>.05)
        elif kind=='sphere':
            center=np.array(params[:3],np.float32);radius=params[3]
            oc=np.array(origin,np.float32)-center
            a=rx*rx+ry*ry+1;b=2*(rx*oc[0]+ry*oc[1]+oc[2]);c=float(oc@oc-radius**2)
            discriminant=b*b-4*a*c
            distance=(-b-np.sqrt(np.maximum(discriminant,0)))/(2*a)
            valid=(discriminant>=0)&(distance>.05)
            for k in range(3):normal[:,:,k]=(origin[k]+rays[k]*distance-center[k])/radius
        else:
            near=[];far=[]
            for axis in range(3):
                with np.errstate(divide='ignore',invalid='ignore'):
                    a=(params[axis]-origin[axis])/rays[axis];b=(params[axis+3]-origin[axis])/rays[axis]
                near.append(np.minimum(a,b));far.append(np.maximum(a,b))
            near=np.stack(near,axis=2);far=np.stack(far,axis=2)
            distance=near.max(axis=2);valid=(distance>.05)&(far.min(axis=2)>=distance)
            face=near.argmax(axis=2)
            for axis in range(3):normal[:,:,axis]=np.where(face==axis,-np.sign(rays[axis]),0)
        hit=valid&(distance<depth)
        if not hit.any():continue
        depth[hit]=distance[hit];ids[hit]=identifier;normals[hit]=normal[hit];colors[hit]=color
    if not np.isfinite(depth).all() or (ids<0).any():raise ValueError('Incomplete analytic scene')
    world=np.stack((camera_x+rx*depth,ry*depth,depth),axis=2)
    floor=ids==1;back=ids==0
    checker=((np.floor(world[:,:,0]*2)+np.floor(world[:,:,2]*2)).astype(np.int32)&1)
    tex=np.ones(depth.shape,np.float32)
    tex[floor]=np.where(checker[floor],.74,1.08)
    stripes=np.sin(world[:,:,0]*9)*np.sin(world[:,:,1]*9)
    tex[back]=1+.13*stripes[back]
    light=np.array([-.35,.75,-.56],np.float32);light/=np.linalg.norm(light)
    illumination=.48+.52*np.maximum(0,normals@light)
    color=np.clip(np.floor(colors*tex[:,:,None]*illumination[:,:,None]+.5),0,255).astype(np.uint8)
    return color,depth,ids


def eye_masks(center_depth,center_ids,eye_depth,eye_ids,camera_x):
    h,w=center_depth.shape;f=.9*w;yy,xx=np.indices((h,w),dtype=np.float32)
    # Eye point back-projected to the central camera; independently test visibility.
    wx=camera_x+((xx+.5-w/2)/f-camera_x/CONVERGENCE_Z)*eye_depth
    cx=f*wx/eye_depth+w/2-.5
    sampled_z=cv2.remap(center_depth,cx,yy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
    sampled_id=cv2.remap(center_ids,cx,yy,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=-1)
    inside=(cx>=2)&(cx<w-3)
    visible=inside&(sampled_id==eye_ids)&(np.abs(sampled_z-eye_depth)<.03)
    # Object silhouettes, not model-predicted boundaries.
    edge=np.zeros((h,w),bool)
    edge[:,1:]|=eye_ids[:,1:]!=eye_ids[:,:-1];edge[:,:-1]|=eye_ids[:,1:]!=eye_ids[:,:-1]
    edge[1:]|=eye_ids[1:]!=eye_ids[:-1];edge[:-1]|=eye_ids[1:]!=eye_ids[:-1]
    edge=cv2.dilate(edge.astype(np.uint8),np.ones((7,7),np.uint8))!=0
    valid=np.ones((h,w),bool);valid[:8]=False;valid[-8:]=False;valid[:,:16]=False;valid[:,-16:]=False
    return dict(all=valid,edges=valid&edge,disoccluded=valid&inside&~visible,
                visible_interior=valid&visible&~edge)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    manifest=dict(completed=False,kind='independent analytic ray intersections and Lambertian procedural surfaces',
        width=WIDTH,height=HEIGHT,focal=.9*WIDTH,baseline_m=BASELINE,convergence_z_m=CONVERGENCE_Z,
        scenes=list(SCENES),frames=17,license='project-authored procedural fixtures; no external media',files=[])
    try:
        for scene in SCENES:
            folder=args.output/scene;folder.mkdir()
            for frame in range(17):
                t=frame/60
                center,z,ids=render(scene,t)
                left,lz,li=render(scene,t,-BASELINE/2)
                right,rz,ri=render(scene,t,BASELINE/2)
                record=dict(inverse_depth=1/z)
                for name,rgb in (('center',center),('left',left),('right',right)):
                    path=folder/f'{frame:02d}-{name}.png'
                    if not cv2.imwrite(str(path),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)):raise RuntimeError('Fixture write failed')
                for side,ez,ei,c in (('left',lz,li,-BASELINE/2),('right',rz,ri,BASELINE/2)):
                    record.update({side+'_'+k:v for k,v in eye_masks(z,ids,ez,ei,c).items()})
                np.savez_compressed(folder/f'{frame:02d}-truth.npz',**record)
            for path in sorted(folder.iterdir()):
                manifest['files'].append(dict(path=str(path.relative_to(args.output)).replace('\\','/'),bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            print(scene,'three-view fixture rendered',flush=True)
        manifest['completed']=True
    finally:(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
