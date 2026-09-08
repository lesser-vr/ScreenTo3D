// Rejected exact-order shared-memory guide candidate. Never loaded by the app.
#define live_post live_post_reference_export
#define live_post_source live_post_source_reference_export
#include "live_depth.cu"
#undef live_post
#undef live_post_source

constexpr int GUIDE_X_THREADS=256,GUIDE_Y_THREADS=8,GUIDE_X_TILE=32,GUIDE_MAX_RADIUS=12;
__global__ void moments_x_shared(LiveDepth c,int radius) {
    __shared__ float guides[GUIDE_X_THREADS+2*GUIDE_MAX_RADIUS];
    __shared__ float depths[GUIDE_X_THREADS+2*GUIDE_MAX_RADIUS];
    int start=int(blockIdx.x)*GUIDE_X_THREADS,y=int(blockIdx.y);
    int valid=min(GUIDE_X_THREADS,c.w-start),count=valid+2*radius;
    for(int t=int(threadIdx.x);t<count;t+=GUIDE_X_THREADS) {
        int x=reflect(start+t-radius,c.w),i=y*c.w+x;
        guides[t]=c.guide[i];depths[t]=c.smooth[i];
    }
    __syncthreads();int x=start+int(threadIdx.x);if(int(threadIdx.x)>=valid)return;
    double si=0,sp=0,sip=0,sii=0;int center=int(threadIdx.x)+radius;
    for(int dx=-radius;dx<=radius;dx++) {float g=guides[center+dx],p=depths[center+dx];
        si+=g;sp+=p;sip+=g*p;sii+=g*g;}
    int i=y*c.w+x;c.t0[i]=float(si);c.t1[i]=float(sp);c.t2[i]=float(sip);c.t3[i]=float(sii);
}
__global__ void coefficients_shared(LiveDepth c,int radius) {
    constexpr int tile=GUIDE_X_TILE*(GUIDE_Y_THREADS+2*GUIDE_MAX_RADIUS);
    __shared__ float s0[tile],s1[tile],s2[tile],s3[tile];
    int x0=int(blockIdx.x)*GUIDE_X_TILE,y0=int(blockIdx.y)*GUIDE_Y_THREADS;
    int lane=int(threadIdx.y)*GUIDE_X_TILE+int(threadIdx.x);
    int valid_y=min(GUIDE_Y_THREADS,c.h-y0),rows=valid_y+2*radius,total=rows*GUIDE_X_TILE;
    for(int q=lane;q<total;q+=GUIDE_X_TILE*GUIDE_Y_THREADS) {
        int x=x0+q%GUIDE_X_TILE,ly=q/GUIDE_X_TILE;
        if(x<c.w) {int i=reflect(y0+ly-radius,c.h)*c.w+x;
            s0[q]=c.t0[i];s1[q]=c.t1[i];s2[q]=c.t2[i];s3[q]=c.t3[i];}
    }
    __syncthreads();int x=x0+int(threadIdx.x),y=y0+int(threadIdx.y);
    if(x>=c.w || int(threadIdx.y)>=valid_y)return;
    double si=0,sp=0,sip=0,sii=0;int center=(int(threadIdx.y)+radius)*GUIDE_X_TILE+int(threadIdx.x);
    for(int dy=-radius;dy<=radius;dy++) {int q=center+dy*GUIDE_X_TILE;
        si+=s0[q];sp+=s1[q];sip+=s2[q];sii+=s3[q];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    float mi=float(si*scale),mp=float(sp*scale),mip=float(sip*scale),mii=float(sii*scale);
    int i=y*c.w+x;c.a[i]=(mip-mi*mp)/(fmaxf(mii-mi*mi,0.f)+.0001f);c.b[i]=mp-c.a[i]*mi;
}
__global__ void coefficients_x_shared(LiveDepth c,int radius) {
    __shared__ float sa[GUIDE_X_THREADS+2*GUIDE_MAX_RADIUS];
    __shared__ float sb[GUIDE_X_THREADS+2*GUIDE_MAX_RADIUS];
    int start=int(blockIdx.x)*GUIDE_X_THREADS,y=int(blockIdx.y);
    int valid=min(GUIDE_X_THREADS,c.w-start),count=valid+2*radius;
    for(int t=int(threadIdx.x);t<count;t+=GUIDE_X_THREADS) {
        int i=y*c.w+reflect(start+t-radius,c.w);sa[t]=c.a[i];sb[t]=c.b[i];
    }
    __syncthreads();int x=start+int(threadIdx.x);if(int(threadIdx.x)>=valid)return;
    double a=0,b=0;int center=int(threadIdx.x)+radius;
    for(int dx=-radius;dx<=radius;dx++){a+=sa[center+dx];b+=sb[center+dx];}
    int i=y*c.w+x;c.t0[i]=float(a);c.t1[i]=float(b);
}
__global__ void guided_shared(LiveDepth c,int radius) {
    constexpr int tile=GUIDE_X_TILE*(GUIDE_Y_THREADS+2*GUIDE_MAX_RADIUS);
    __shared__ float sa[tile],sb[tile];
    int x0=int(blockIdx.x)*GUIDE_X_TILE,y0=int(blockIdx.y)*GUIDE_Y_THREADS;
    int lane=int(threadIdx.y)*GUIDE_X_TILE+int(threadIdx.x);
    int valid_y=min(GUIDE_Y_THREADS,c.h-y0),rows=valid_y+2*radius,total=rows*GUIDE_X_TILE;
    for(int q=lane;q<total;q+=GUIDE_X_TILE*GUIDE_Y_THREADS) {
        int x=x0+q%GUIDE_X_TILE,ly=q/GUIDE_X_TILE;
        if(x<c.w) {int i=reflect(y0+ly-radius,c.h)*c.w+x;sa[q]=c.t0[i];sb[q]=c.t1[i];}
    }
    __syncthreads();int x=x0+int(threadIdx.x),y=y0+int(threadIdx.y);
    if(x>=c.w || int(threadIdx.y)>=valid_y)return;
    double a=0,b=0;int center=(int(threadIdx.y)+radius)*GUIDE_X_TILE+int(threadIdx.x);
    for(int dy=-radius;dy<=radius;dy++){int q=center+dy*GUIDE_X_TILE;a+=sa[q];b+=sb[q];}
    double scale=1.0/((2*radius+1)*(2*radius+1));int i=y*c.w+x;
    c.aligned[i]=fminf(1.f,fmaxf(0.f,float(a*scale)*c.guide[i]+float(b*scale)));
}
static cudaError_t shared_guide(LiveDepth* c,int radius,cudaStream_t stream) {
    dim3 rows((c->w+GUIDE_X_THREADS-1)/GUIDE_X_THREADS,c->h);
    dim3 tiles((c->w+GUIDE_X_TILE-1)/GUIDE_X_TILE,(c->h+GUIDE_Y_THREADS-1)/GUIDE_Y_THREADS);
    moments_x_shared<<<rows,GUIDE_X_THREADS,0,stream>>>(*c,radius);
    coefficients_shared<<<tiles,dim3(GUIDE_X_TILE,GUIDE_Y_THREADS),0,stream>>>(*c,radius);
    coefficients_x_shared<<<rows,GUIDE_X_THREADS,0,stream>>>(*c,radius);
    guided_shared<<<tiles,dim3(GUIDE_X_TILE,GUIDE_Y_THREADS),0,stream>>>(*c,radius);
    return cudaGetLastError();
}
extern "C" __declspec(dllexport) int live_post(void* handle,const unsigned char* rgb,
    const float* device_depth,int radius,double alpha,float color_threshold,float depth_threshold,int reset,
    float* diagnostic,double transition) {
    auto c=(LiveDepth*)handle;if(!c || !rgb || !device_depth || radius<1 || radius>12)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[2],s));C(cudaMemcpyAsync(c->rgb,rgb,c->n*3,cudaMemcpyHostToDevice,s));
    C(cudaMemsetAsync(c->invalid,0,4,s));check_raw<<<(518*518+255)/256,256,0,s>>>(device_depth,c->invalid);
    resize_depth<<<blocks,256,0,s>>>(device_depth,c->resized,c->w,c->h,c->invalid);C(cudaGetLastError());
    C(cudaEventRecord(c->events[3],s));C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    limits<<<1,1,0,s>>>(c->sorted,c->bounds,c->n,alpha,reset);C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    temporal<<<blocks,256,0,s>>>(*c,float(alpha),float(1.0-alpha),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));C(shared_guide(c,radius,s));C(cudaEventRecord(c->events[6],s));
    C(cudaMemcpyAsync(c->previous,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,s));
    if(diagnostic)C(cudaMemcpyAsync(diagnostic,c->aligned,c->n*4,cudaMemcpyDeviceToHost,s));return 0;
#undef C
}
extern "C" __declspec(dllexport) int live_post_source(void* handle,const unsigned char* rgb,
    const float* depth,int depth_on_device,int radius,double alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition) {
    auto c=(LiveDepth*)handle;if(!c || !rgb || !depth || (depth_on_device!=0 && depth_on_device!=1) || radius<1 || radius>12)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[2],s));C(cudaMemcpyAsync(c->rgb,rgb,c->n*3,cudaMemcpyHostToDevice,s));
    C(cudaMemsetAsync(c->invalid,0,4,s));C(cudaMemcpyAsync(c->resized,depth,c->n*4,depth_on_device?cudaMemcpyDeviceToDevice:cudaMemcpyHostToDevice,s));
    check_source_raw<<<blocks,256,0,s>>>(c->resized,c->n,c->invalid);C(cudaGetLastError());C(cudaEventRecord(c->events[3],s));
    C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    limits<<<1,1,0,s>>>(c->sorted,c->bounds,c->n,alpha,reset);C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    temporal<<<blocks,256,0,s>>>(*c,float(alpha),float(1.0-alpha),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));C(shared_guide(c,radius,s));C(cudaEventRecord(c->events[6],s));
    C(cudaMemcpyAsync(c->previous,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,s));
    if(diagnostic)C(cudaMemcpyAsync(diagnostic,c->aligned,c->n*4,cudaMemcpyDeviceToHost,s));return 0;
#undef C
}
