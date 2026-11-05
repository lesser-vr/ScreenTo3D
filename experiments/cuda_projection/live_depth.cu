// Local device-resident DA2 postprocess candidate. Existing projection is reused.
#define DEPTHSBS_GPU_PREVIEW 1
#include "projection.cu"
#include "resolve_parallel.cuh"
#include <cub/device/device_radix_sort.cuh>

struct LiveDepth {
    int w, h, n; cudaStream_t stream;
    float *resized=nullptr, *sorted=nullptr, *smooth=nullptr, *guide=nullptr;
    float *a=nullptr, *b=nullptr, *t0=nullptr, *t1=nullptr, *t2=nullptr, *t3=nullptr;
    float *aligned=nullptr, *shift=nullptr;
    unsigned char *rgb=nullptr, *previous=nullptr, *output=nullptr, *motion=nullptr;
    unsigned long long* owners=nullptr;
    double* bounds=nullptr; int* invalid=nullptr;
    void* scratch=nullptr; size_t scratch_bytes=0;
    unsigned char* small_rgb=nullptr;
    cudaEvent_t events[9]={};
    bool parallel_resolve=false;
    cudaEvent_t projection_events[7]={};
};

static cudaError_t live_release(LiveDepth* c) {
    if (!c) return cudaSuccess;
    auto status=cudaStreamSynchronize(c->stream);
    for(auto event:c->events)if(event){auto e=cudaEventDestroy(event);if(status==cudaSuccess)status=e;}
    for(auto event:c->projection_events)if(event){auto e=cudaEventDestroy(event);if(status==cudaSuccess)status=e;}
    for (void* p : std::initializer_list<void*>{c->resized,c->sorted,c->smooth,c->guide,
        c->a,c->b,c->t0,c->t1,c->t2,c->t3,c->aligned,c->shift,
        static_cast<void*>(c->rgb),c->previous,c->output,c->motion,
        static_cast<void*>(c->owners),static_cast<void*>(c->bounds),
        static_cast<void*>(c->invalid),c->scratch,c->small_rgb}) {
        if(p) { auto e=cudaFree(p); if(status==cudaSuccess) status=e; }
    }
    delete c; return status;
}

extern "C" __declspec(dllexport) int live_create(void** out,int w,int h,void* stream) {
    if(!out || !stream || w<16 || h<16 || w>4096 || h>2160) return 1;
    *out=nullptr; auto c=new(std::nothrow) LiveDepth{w,h,w*h,(cudaStream_t)stream};
    if(!c) return 2;
    auto allocate=[&]()->cudaError_t {
#define C(call) do {auto e=(call); if(e!=cudaSuccess)return e;}while(0)
        for(float** p:{&c->resized,&c->sorted,&c->smooth,&c->guide,&c->a,&c->b,
                      &c->t0,&c->t1,&c->t2,&c->t3,&c->aligned,&c->shift}) C(cudaMalloc(p,c->n*4));
        C(cudaMalloc(&c->rgb,c->n*3)); C(cudaMalloc(&c->previous,c->n*3));
        C(cudaMalloc(&c->output,c->n*3)); C(cudaMalloc(&c->motion,c->n));
        C(cudaMalloc(&c->owners,c->n*8)); C(cudaMalloc(&c->bounds,16));
        C(cudaMalloc(&c->invalid,4));
        C(cudaMalloc(&c->small_rgb,518*518*3));
        for(auto& event:c->events)C(cudaEventCreate(&event));
        for(auto& event:c->projection_events)C(cudaEventCreate(&event));
        C(cub::DeviceRadixSort::SortKeys(nullptr,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,c->stream));
        C(cudaMalloc(&c->scratch,c->scratch_bytes)); return cudaSuccess;
#undef C
    };
    auto status=allocate(); if(status!=cudaSuccess) {live_release(c);return int(status);}
    *out=c; return 0;
}
extern "C" __declspec(dllexport) int live_destroy(void* p) {return int(live_release((LiveDepth*)p));}
extern "C" __declspec(dllexport) int live_set_parallel(void* p,int enabled) {
    if(!p || (enabled!=0 && enabled!=1))return 1;
    static_cast<LiveDepth*>(p)->parallel_resolve=enabled!=0;return 0;
}

__device__ int reflect(int x,int n) {return x<0 ? -x-1 : x>=n ? 2*n-x-1 : x;}
__global__ void input_normalize(const unsigned char* rgb,float* tensor) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=518*518)return;
    const float mean[3]={.485f,.456f,.406f},std[3]={.229f,.224f,.225f};
    for(int c=0;c<3;c++)tensor[c*518*518+i]=(float(rgb[i*3+c])/255.f-mean[c])/std[c];
}
extern "C" __declspec(dllexport) int live_prepare(void* handle,const unsigned char* small_rgb,float* input) {
    auto c=(LiveDepth*)handle;if(!c || !small_rgb || !input)return 1;
    auto e=cudaEventRecord(c->events[0],c->stream);
    if(e==cudaSuccess)e=cudaMemcpyAsync(c->small_rgb,small_rgb,518*518*3,cudaMemcpyHostToDevice,c->stream);
    if(e==cudaSuccess) {
        input_normalize<<<(518*518+255)/256,256,0,c->stream>>>(c->small_rgb,input);
        e=cudaGetLastError();
    }
    if(e==cudaSuccess)e=cudaEventRecord(c->events[1],c->stream);
    if(e!=cudaSuccess)cudaStreamSynchronize(c->stream);
    return int(e);
}
__device__ void cubic(float x,float* c) {
    const float A=-.75f;
    c[0]=((A*(x+1)-5*A)*(x+1)+8*A)*(x+1)-4*A;
    c[1]=((A+2)*x-(A+3))*x*x+1;
    c[2]=((A+2)*(1-x)-(A+3))*(1-x)*(1-x)+1;
    c[3]=1-c[0]-c[1]-c[2];
}
__global__ void resize_depth(const float* src,float* dst,int w,int h,int* invalid) {
    int i=blockIdx.x*blockDim.x+threadIdx.x; if(i>=w*h)return;
    double px=(i%w+.5)*(518.0/w)-.5,py=(i/w+.5)*(518.0/h)-.5;
    int sx=int(floor(px)),sy=int(floor(py));
    float fx=float(px-sx),fy=float(py-sy);
    float ax[4],ay[4];cubic(fx,ax);cubic(fy,ay);
    float v=0;
    for(int y=0;y<4;y++) { float row=0;
        for(int x=0;x<4;x++) row+=src[max(0,min(517,sy+y-1))*518+max(0,min(517,sx+x-1))]*ax[x];
        v+=row*ay[y];
    }
    if(!isfinite(v)) atomicExch(invalid,1);
    dst[i]=v;
}
__global__ void check_raw(const float* src,int* invalid) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<518*518 && !isfinite(src[i]))atomicExch(invalid,1);
}
__global__ void check_source_raw(const float* src,int n,int* invalid) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<n && !isfinite(src[i]))atomicExch(invalid,1);
}
__global__ void limits(const float* sorted,double* bounds,int n,double alpha,int reset) {
    for(int k=0;k<2;k++) {
        double pos=(n-1)*(k?.98:.02);int index=int(pos);double t=pos-index;
        float lo=sorted[index],hi=sorted[min(n-1,index+1)],diff=hi-lo;
        float value=float(t>=.5 ? double(hi)-double(diff)*(1-t) : double(lo)+double(diff)*t);
        bounds[k]=reset ? double(value) : double(alpha)*double(value)+(1.0-double(alpha))*bounds[k];
    }
}
__global__ void normalize_motion(LiveDepth c,float threshold,int reset) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    float lo=float(c.bounds[0]),range=float(fmax(c.bounds[1]-c.bounds[0],1e-6));
    c.resized[i]=fminf(1.f,fmaxf(0.f,(c.resized[i]-lo)/range));
    int diff=0;if(!reset)for(int k=0;k<3;k++)diff=max(diff,abs(int(c.rgb[i*3+k])-int(c.previous[i*3+k])));
    c.motion[i]=!reset && float(diff)/255.f>threshold;
    int r=c.rgb[i*3],g=c.rgb[i*3+1],b=c.rgb[i*3+2];
    c.guide[i]=float((r*9798+g*19235+b*3735+16384)>>15)/255.f;
}
__global__ void temporal(LiveDepth c,float alpha,float complement,float threshold,float transition,float start,int reset) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    bool changed=false;int x=i%c.w,y=i/c.w;
    if(!reset)for(int dy=-3;dy<=3 && !changed;dy++)for(int dx=-3;dx<=3;dx++) {
        int xx=x+dx,yy=y+dy;if(xx>=0 && xx<c.w && yy>=0 && yy<c.h && c.motion[yy*c.w+xx])changed=true;
    }
    float v=c.resized[i];
    float delta=fabsf(v-c.smooth[i]);
    if(!reset && !changed && delta<=threshold) {
        if(transition>0.f && delta<threshold) {
            float ramp=fminf(1.f,fmaxf(0.f,(delta-start)/transition));
            float weight=alpha+complement*ramp;
            v=weight*v+(1.f-weight)*c.smooth[i];
        } else if(transition<=0.f) v=alpha*v+complement*c.smooth[i];
    }
    c.smooth[i]=v;
}
// Four guide moments, separable reflected box filters; double summation.
__global__ void moments_x(LiveDepth c,int radius) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    int x=i%c.w,row=i-x;double si=0,sp=0,sip=0,sii=0;
    for(int dx=-radius;dx<=radius;dx++) {int j=row+reflect(x+dx,c.w);float g=c.guide[j],p=c.smooth[j];
        si+=g;sp+=p;sip+=g*p;sii+=g*g;}
    c.t0[i]=float(si);c.t1[i]=float(sp);c.t2[i]=float(sip);c.t3[i]=float(sii);
}
__global__ void coefficients(LiveDepth c,int radius) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    int x=i%c.w,y=i/c.w;double si=0,sp=0,sip=0,sii=0;
    for(int dy=-radius;dy<=radius;dy++) {int j=reflect(y+dy,c.h)*c.w+x;
        si+=c.t0[j];sp+=c.t1[j];sip+=c.t2[j];sii+=c.t3[j];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    float mi=float(si*scale),mp=float(sp*scale),mip=float(sip*scale),mii=float(sii*scale);
    c.a[i]=(mip-mi*mp)/(fmaxf(mii-mi*mi,0.f)+.0001f);c.b[i]=mp-c.a[i]*mi;
}
__global__ void coefficients_x(LiveDepth c,int radius) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    int x=i%c.w,row=i-x;double a=0,b=0;
    for(int dx=-radius;dx<=radius;dx++){int j=row+reflect(x+dx,c.w);a+=c.a[j];b+=c.b[j];}
    c.t0[i]=float(a);c.t1[i]=float(b);
}
__global__ void guided(LiveDepth c,int radius) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    int x=i%c.w,y=i/c.w;double a=0,b=0;
    for(int dy=-radius;dy<=radius;dy++){int j=reflect(y+dy,c.h)*c.w+x;a+=c.t0[j];b+=c.t1[j];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    c.aligned[i]=fminf(1.f,fmaxf(0.f,float(a*scale)*c.guide[i]+float(b*scale)));
}
// Radius 4 remains on the exact direct-sum kernels above. Wider live guide
// windows use bounded chunks so each thread updates a 64-pixel rolling sum.
#ifndef DEPTHSBS_GUIDE_REFERENCE_ONLY
constexpr int GUIDE_CHUNK=64;
__global__ void moments_x_rolling(LiveDepth c,int radius) {
    int segments=(c.w+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int y=id/segments,segment=id%segments,x0=segment*GUIDE_CHUNK;if(y>=c.h)return;
    int end=min(c.w,x0+GUIDE_CHUNK),row=y*c.w;double si=0,sp=0,sip=0,sii=0;
    for(int dx=-radius;dx<=radius;dx++) {int j=row+reflect(x0+dx,c.w);float g=c.guide[j],p=c.smooth[j];
        si+=g;sp+=p;sip+=g*p;sii+=g*g;}
    for(int x=x0;x<end;x++) {
        int i=row+x;c.t0[i]=float(si);c.t1[i]=float(sp);c.t2[i]=float(sip);c.t3[i]=float(sii);
        if(x+1<end) {int old=row+reflect(x-radius,c.w),next=row+reflect(x+radius+1,c.w);
            float og=c.guide[old],op=c.smooth[old],ng=c.guide[next],np=c.smooth[next];
            si-=og;sp-=op;sip-=og*op;sii-=og*og;si+=ng;sp+=np;sip+=ng*np;sii+=ng*ng;}
    }
}
__global__ void coefficients_y_rolling(LiveDepth c,int radius) {
    int chunks=(c.h+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int chunk=id/c.w,x=id%c.w,y0=chunk*GUIDE_CHUNK;if(chunk>=chunks)return;
    int end=min(c.h,y0+GUIDE_CHUNK);double si=0,sp=0,sip=0,sii=0;
    for(int dy=-radius;dy<=radius;dy++) {int j=reflect(y0+dy,c.h)*c.w+x;
        si+=c.t0[j];sp+=c.t1[j];sip+=c.t2[j];sii+=c.t3[j];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    for(int y=y0;y<end;y++) {
        float mi=float(si*scale),mp=float(sp*scale),mip=float(sip*scale),mii=float(sii*scale);
        int i=y*c.w+x;c.a[i]=(mip-mi*mp)/(fmaxf(mii-mi*mi,0.f)+.0001f);c.b[i]=mp-c.a[i]*mi;
        if(y+1<end) {int old=reflect(y-radius,c.h)*c.w+x,next=reflect(y+radius+1,c.h)*c.w+x;
            si-=c.t0[old];sp-=c.t1[old];sip-=c.t2[old];sii-=c.t3[old];
            si+=c.t0[next];sp+=c.t1[next];sip+=c.t2[next];sii+=c.t3[next];}
    }
}
__global__ void coefficients_x_rolling(LiveDepth c,int radius) {
    int segments=(c.w+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int y=id/segments,segment=id%segments,x0=segment*GUIDE_CHUNK;if(y>=c.h)return;
    int end=min(c.w,x0+GUIDE_CHUNK),row=y*c.w;double a=0,b=0;
    for(int dx=-radius;dx<=radius;dx++){int j=row+reflect(x0+dx,c.w);a+=c.a[j];b+=c.b[j];}
    for(int x=x0;x<end;x++) {
        int i=row+x;c.t0[i]=float(a);c.t1[i]=float(b);
        if(x+1<end) {int old=row+reflect(x-radius,c.w),next=row+reflect(x+radius+1,c.w);
            a-=c.a[old];b-=c.b[old];a+=c.a[next];b+=c.b[next];}
    }
}
__global__ void guided_y_rolling(LiveDepth c,int radius) {
    int chunks=(c.h+GUIDE_CHUNK-1)/GUIDE_CHUNK,id=blockIdx.x*blockDim.x+threadIdx.x;
    int chunk=id/c.w,x=id%c.w,y0=chunk*GUIDE_CHUNK;if(chunk>=chunks)return;
    int end=min(c.h,y0+GUIDE_CHUNK);double a=0,b=0;
    for(int dy=-radius;dy<=radius;dy++){int j=reflect(y0+dy,c.h)*c.w+x;a+=c.t0[j];b+=c.t1[j];}
    double scale=1.0/((2*radius+1)*(2*radius+1));
    for(int y=y0;y<end;y++) {
        int i=y*c.w+x;c.aligned[i]=fminf(1.f,fmaxf(0.f,float(a*scale)*c.guide[i]+float(b*scale)));
        if(y+1<end) {int old=reflect(y-radius,c.h)*c.w+x,next=reflect(y+radius+1,c.h)*c.w+x;
            a-=c.t0[old];b-=c.t1[old];a+=c.t0[next];b+=c.t1[next];}
    }
}
static cudaError_t live_guide(LiveDepth* c,int radius,cudaStream_t stream) {
    if(radius<=4) {
        int blocks=(c->n+255)/256;
        moments_x<<<blocks,256,0,stream>>>(*c,radius);
        coefficients<<<blocks,256,0,stream>>>(*c,radius);
        coefficients_x<<<blocks,256,0,stream>>>(*c,radius);
        guided<<<blocks,256,0,stream>>>(*c,radius);
        return cudaGetLastError();
    }
    int horizontal=c->h*((c->w+GUIDE_CHUNK-1)/GUIDE_CHUNK);
    int vertical=c->w*((c->h+GUIDE_CHUNK-1)/GUIDE_CHUNK);
    moments_x_rolling<<<(horizontal+255)/256,256,0,stream>>>(*c,radius);
    coefficients_y_rolling<<<(vertical+255)/256,256,0,stream>>>(*c,radius);
    coefficients_x_rolling<<<(horizontal+255)/256,256,0,stream>>>(*c,radius);
    guided_y_rolling<<<(vertical+255)/256,256,0,stream>>>(*c,radius);
    return cudaGetLastError();
}
#endif
__global__ void make_shift(LiveDepth c,float convergence,float scale) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<c.n)c.shift[i]=-(c.aligned[i]-convergence)*scale*.5f;
}

static int live_post_impl(void* handle,const unsigned char* rgb,
    const float* device_depth,int radius,double alpha,float color_threshold,float depth_threshold,int reset,
    float* diagnostic,double transition,bool rgb_device) {
    auto c=(LiveDepth*)handle;if(!c || !rgb || !device_depth || radius<1 || radius>12)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[2],s));
    C(cudaMemcpyAsync(c->rgb,rgb,c->n*3,rgb_device?cudaMemcpyDeviceToDevice:cudaMemcpyHostToDevice,s));
    C(cudaMemsetAsync(c->invalid,0,4,s));
    check_raw<<<(518*518+255)/256,256,0,s>>>(device_depth,c->invalid);
    resize_depth<<<blocks,256,0,s>>>(device_depth,c->resized,c->w,c->h,c->invalid);
    C(cudaGetLastError());
    C(cudaEventRecord(c->events[3],s));
    C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    limits<<<1,1,0,s>>>(c->sorted,c->bounds,c->n,alpha,reset);
    C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    temporal<<<blocks,256,0,s>>>(*c,float(alpha),float(1.0-alpha),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));
#ifdef DEPTHSBS_GUIDE_REFERENCE_ONLY
    moments_x<<<blocks,256,0,s>>>(*c,radius);
    coefficients<<<blocks,256,0,s>>>(*c,radius);
    coefficients_x<<<blocks,256,0,s>>>(*c,radius);
    guided<<<blocks,256,0,s>>>(*c,radius);C(cudaGetLastError());
#else
    C(live_guide(c,radius,s));
#endif
    C(cudaEventRecord(c->events[6],s));
    C(cudaMemcpyAsync(c->previous,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,s));
    if(diagnostic)C(cudaMemcpyAsync(diagnostic,c->aligned,c->n*4,cudaMemcpyDeviceToHost,s));
    return 0;
#undef C
}

// oVDA/VDA device-depth spike only: raw depth is already source resolution.
extern "C" __declspec(dllexport) int live_post(void* handle,const unsigned char* rgb,
    const float* depth,int radius,double alpha,float ct,float dt,int reset,float* diagnostic,double transition) {
    return live_post_impl(handle,rgb,depth,radius,alpha,ct,dt,reset,diagnostic,transition,false);
}
extern "C" __declspec(dllexport) int live_post_gpu(void* handle,const unsigned char* rgb,
    const float* depth,int radius,double alpha,float ct,float dt,int reset,float* diagnostic,double transition) {
    return live_post_impl(handle,rgb,depth,radius,alpha,ct,dt,reset,diagnostic,transition,true);
}

// depth_on_device=1 requires the pointer to be produced on this exact stream.
extern "C" __declspec(dllexport) int live_post_source(void* handle,const unsigned char* rgb,
    const float* depth,int depth_on_device,int radius,double alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition) {
    auto c=(LiveDepth*)handle;
    // 2: both RGB and source depth are owned device buffers on this stream.
    if(!c || !rgb || !depth || depth_on_device<0 || depth_on_device>2 || radius<1 || radius>12)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[2],s));
    C(cudaMemcpyAsync(c->rgb,rgb,c->n*3,depth_on_device==2?cudaMemcpyDeviceToDevice:cudaMemcpyHostToDevice,s));
    C(cudaMemsetAsync(c->invalid,0,4,s));
    C(cudaMemcpyAsync(c->resized,depth,c->n*4,depth_on_device?cudaMemcpyDeviceToDevice:cudaMemcpyHostToDevice,s));
    check_source_raw<<<blocks,256,0,s>>>(c->resized,c->n,c->invalid);C(cudaGetLastError());
    C(cudaEventRecord(c->events[3],s));
    C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    limits<<<1,1,0,s>>>(c->sorted,c->bounds,c->n,alpha,reset);
    C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    temporal<<<blocks,256,0,s>>>(*c,float(alpha),float(1.0-alpha),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));
    moments_x<<<blocks,256,0,s>>>(*c,radius);
    coefficients<<<blocks,256,0,s>>>(*c,radius);
    coefficients_x<<<blocks,256,0,s>>>(*c,radius);
    guided<<<blocks,256,0,s>>>(*c,radius);C(cudaGetLastError());
    C(cudaEventRecord(c->events[6],s));
    C(cudaMemcpyAsync(c->previous,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,s));
    if(diagnostic)C(cudaMemcpyAsync(diagnostic,c->aligned,c->n*4,cudaMemcpyDeviceToHost,s));
    return 0;
#undef C
}
extern "C" __declspec(dllexport) int live_project(void* handle,const float* refined,
    float convergence,float scale,int coverage,unsigned char* left,unsigned char* right,int* invalid) {
    auto c=(LiveDepth*)handle;if(!c || !left || !right || !invalid)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[7],s));
    if(refined)C(cudaMemcpyAsync(c->aligned,refined,c->n*4,cudaMemcpyHostToDevice,s));
    make_shift<<<blocks,256,0,s>>>(*c,convergence,scale);
    C(cudaEventRecord(c->projection_events[0],s));
    for(int eye=0;eye<2;eye++) {
        if(eye)negate_shift<<<blocks,256,0,s>>>(c->shift,c->n);
        C(cudaMemsetAsync(c->owners,0,c->n*8,s));
        splat<<<blocks,256,0,s>>>(c->aligned,c->shift,c->owners,c->w,c->n,coverage!=0);
        C(cudaEventRecord(c->projection_events[eye*3+1],s));
        if(c->parallel_resolve)
            launch_resolve_parallel(c->rgb,c->owners,c->output,c->w,c->h,s);
        else
            resolve<<<(c->h+63)/64,64,0,s>>>(c->rgb,c->owners,c->output,c->w,c->h);
        C(cudaGetLastError());
        C(cudaEventRecord(c->projection_events[eye*3+2],s));
        C(cudaMemcpyAsync(eye?right:left,c->output,c->n*3,cudaMemcpyDeviceToHost,s));
        C(cudaEventRecord(c->projection_events[eye*3+3],s));
    }
    C(cudaMemcpyAsync(invalid,c->invalid,4,cudaMemcpyDeviceToHost,s));
    C(cudaEventRecord(c->events[8],s));
    C(cudaStreamSynchronize(s));return 0;
#undef C
}
extern "C" __declspec(dllexport) int live_times(void* handle,float* ms) {
    auto c=(LiveDepth*)handle;if(!c || !ms)return 1;
    for(int i=0;i<8;i++) {
        auto e=cudaEventElapsedTime(ms+i,c->events[i],c->events[i+1]);
        if(e!=cudaSuccess)return int(e);
    }
    return 0;
}
extern "C" __declspec(dllexport) int live_projection_times(void* handle,float* ms) {
    auto c=(LiveDepth*)handle;if(!c || !ms)return 1;
    for(int i=0;i<6;i++) {
        auto e=cudaEventElapsedTime(ms+i,c->projection_events[i],c->projection_events[i+1]);
        if(e!=cudaSuccess)return int(e);
    }
    return 0;
}

// Explicit diagnostic readback only; never called by the live worker.
extern "C" __declspec(dllexport) int live_resize_probe(void* handle,const float* depth,float* output) {
    auto c=(LiveDepth*)handle;if(!c || !depth || !output)return 1;
    resize_depth<<<(c->n+255)/256,256,0,c->stream>>>(depth,c->t0,c->w,c->h,c->invalid);
    auto e=cudaGetLastError();
    if(e==cudaSuccess)e=cudaMemcpyAsync(output,c->t0,c->n*4,cudaMemcpyDeviceToHost,c->stream);
    auto sync=cudaStreamSynchronize(c->stream);return int(e==cudaSuccess?sync:e);
}
extern "C" __declspec(dllexport) int live_snapshot(void* handle,float* normalized,float* smooth,double* bounds) {
    auto c=(LiveDepth*)handle;if(!c || !normalized || !smooth || !bounds)return 1;
    auto s=c->stream;
    auto e=cudaMemcpyAsync(normalized,c->resized,c->n*4,cudaMemcpyDeviceToHost,s);
    if(e==cudaSuccess)e=cudaMemcpyAsync(smooth,c->smooth,c->n*4,cudaMemcpyDeviceToHost,s);
    if(e==cudaSuccess)e=cudaMemcpyAsync(bounds,c->bounds,16,cudaMemcpyDeviceToHost,s);
    auto synced=cudaStreamSynchronize(s);return int(e==cudaSuccess?synced:e);
}
