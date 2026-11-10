// oVDA postprocessing adaptation, NC-SA-UHDV1.0; see LICENSE/README.md.
// Borrow the unchanged LiveDepth layout; allocate/destroy it through its owner.
#include "../cuda_projection/live_depth.cu"

struct OvdaRange { float* anchors;double dt,deadband,expand,contract; };

__device__ bool ovda_transport(LiveDepth c,const float* anchors,double& low,double& high) {
    double span=fmax(high-low,1e-6);
    __shared__ double sums[6][256],gain,offset;
    __shared__ int initial,accepted;
    int tid=threadIdx.x;
    if(tid==0){gain=1;offset=0;initial=0;accepted=1;}
    double a[4],b[4];bool valid[4];
    for(int q=0;q<4;q++) {
        int p=tid+q*256;
        int x=min(((p%32)*2+1)*c.w/64,c.w-1),y=min(((p/32)*2+1)*c.h/64,c.h-1);
        a[q]=(double(anchors[p])-low)/span;b[q]=(double(c.resized[y*c.w+x])-low)/span;
        bool changed=a[q]<=.05||a[q]>=.95||!isfinite(b[q]);
        for(int dy=-1;dy<=1&&!changed;dy++)for(int dx=-1;dx<=1;dx++) {
            int j=min(max(y+dy,0),c.h-1)*c.w+min(max(x+dx,0),c.w-1);
            for(int k=0;k<3;k++)if(abs(int(c.rgb[j*3+k])-int(c.previous[j*3+k]))>4)changed=true;
        }
        valid[q]=!changed;
    }
    __syncthreads();
    for(int pass=0;pass<2;pass++) {
        double sx=0,sy=0,sxx=0,sxy=0,syy=0;int count=0;
        for(int q=0;q<4;q++) {
            if(!valid[q]||(pass&&fabs(b[q]-(gain*a[q]+offset))>.025))continue;
            sx+=a[q];sy+=b[q];sxx+=a[q]*a[q];sxy+=a[q]*b[q];syy+=b[q]*b[q];++count;
        }
        sums[0][tid]=sx;sums[1][tid]=sy;sums[2][tid]=sxx;
        sums[3][tid]=sxy;sums[4][tid]=syy;sums[5][tid]=count;
        __syncthreads();
        for(int stride=128;stride;stride/=2){
            if(tid<stride)for(int k=0;k<6;k++)sums[k][tid]+=sums[k][tid+stride];
            __syncthreads();
        }
        if(tid==0) {
            sx=sums[0][0];sy=sums[1][0];sxx=sums[2][0];sxy=sums[3][0];syy=sums[4][0];count=int(sums[5][0]);
            if(count<96||(pass&&count<initial*.8))accepted=0;
            if(accepted) {
                double variance=sxx-sx*sx/count;
                if(variance/count<.005)accepted=0;
                else {
                    gain=(sxy-sx*sy/count)/variance;offset=(sy-gain*sx)/count;
                    if(gain<.8||gain>1.25||fabs(offset)>.15)accepted=0;
                    if(pass) {
                        double residual=fmax(0.,(syy+gain*gain*sxx+count*offset*offset-2*gain*sxy-2*offset*sy+2*gain*offset*sx)/count);
                        if(residual>.015*.015)accepted=0;
                    } else initial=count;
                }
            }
        }
        __syncthreads();
        if(!accepted)return false;
    }
    if(tid==0){high=low+(offset+gain)*span;low+=offset*span;}
    return true;
}

__global__ void ovda_limits(LiveDepth c,OvdaRange parameters,int reset) {
    int tid=threadIdx.x;
    if(!reset)ovda_transport(c,parameters.anchors,c.bounds[0],c.bounds[1]);
    // Keep raw anchors, never the pixel EMA: range adaptation must not be fed
    // back as an apparent model scale change on the next frame.
    for(int q=0;q<4;q++) {
        int p=tid+q*256;
        int x=min(((p%32)*2+1)*c.w/64,c.w-1),y=min(((p/32)*2+1)*c.h/64,c.h-1);
        parameters.anchors[p]=c.resized[y*c.w+x];
    }
    if(tid)return;
    double target[2];
    for(int k=0;k<2;k++) {
        double pos=(c.n-1)*(k?.98:.02);int index=int(pos);double t=pos-index;
        float lo=c.sorted[index],hi=c.sorted[min(c.n-1,index+1)],difference=hi-lo;
        target[k]=float(t>=.5?double(hi)-double(difference)*(1-t):double(lo)+double(difference)*t);
    }
    if(reset){c.bounds[0]=target[0];c.bounds[1]=target[1];return;}
    double band=parameters.deadband*fmax(fmax(c.bounds[1]-c.bounds[0],target[1]-target[0]),1e-6);
    for(int k=0;k<2;k++) {
        double delta=target[k]-c.bounds[k];
        if(fabs(delta)<=band)continue;
        bool expanding=k==0?delta<0:delta>0;
        double tau=expanding?parameters.expand:parameters.contract;
        c.bounds[k]+=-expm1(-parameters.dt/tau)*delta;
    }
}

static void ovda_range_update(LiveDepth* c,double,int reset,const void* parameters) {
    ovda_limits<<<1,256,0,c->stream>>>(*c,*static_cast<const OvdaRange*>(parameters),reset);
}

extern "C" __declspec(dllexport) int ovda_post_source(void* handle,const unsigned char* rgb,
    const float* depth,int depth_on_device,int radius,double range_alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition,double pixel_alpha) {
    if(!isfinite(pixel_alpha)||pixel_alpha<=0.||pixel_alpha>1.)return 1;
    return live_post_source_impl(handle,rgb,depth,depth_on_device,radius,range_alpha,
        color_threshold,depth_threshold,reset,diagnostic,transition,pixel_alpha);
}

extern "C" __declspec(dllexport) int ovda_post_source_range(void* handle,const unsigned char* rgb,
    const float* depth,int depth_on_device,int radius,double range_alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition,double pixel_alpha,
    float* anchors,double dt,double deadband,double expand,double contract) {
    if(!anchors||!isfinite(pixel_alpha)||pixel_alpha<=0.||pixel_alpha>1.||
       !isfinite(dt)||dt<=0.||dt>.1||!isfinite(deadband)||deadband<0.||deadband>.05||
       !isfinite(expand)||expand<=0.||!isfinite(contract)||contract<expand||contract>10.)return 1;
    OvdaRange parameters={anchors,dt,deadband,expand,contract};
    return live_post_source_impl(handle,rgb,depth,depth_on_device,radius,range_alpha,
        color_threshold,depth_threshold,reset,diagnostic,transition,pixel_alpha,ovda_range_update,&parameters);
}
