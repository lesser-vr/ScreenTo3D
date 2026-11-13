// Local device-resident DA2 postprocess candidate. Existing projection is reused.
#define SCREENTO3D_GPU_PREVIEW 1
#include "projection.cu"
#include "resolve_parallel.cuh"
#include <cub/device/device_radix_sort.cuh>
#include <cfloat>

// A weighted FP32 EMA can stop several ULPs short of its target. Across [0,1]
// this bound contributes under 0.00011 eye pixels at the largest DA2 setting.
constexpr float static_depth_tolerance=8.f*FLT_EPSILON;

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
    // Appended: keep the existing borrowed field prefix unchanged.
    bool subpixel=false;
    float* stereo_samples=nullptr;
    bool continuous_coverage=false;
    double range_dt=-1; // Opt-in source-time range response; legacy EMA when disabled.
    float* window_state=nullptr; // target L/R, displayed L/R; GPU-only normal path.
    double window_dt=-1;
    bool window_reset=true;
    bool disparity_budget=false;
    // Uses existing padding before detail_mode; the borrowed layout is unchanged.
    bool same_input=false;
    int detail_mode=0; // bit 0: selective contour, bit 1: bounded background fill.
};

extern "C" __declspec(dllexport) int live_set_same_input(void* p,int same) {
    if(!p || (same!=0 && same!=1))return 1;
    static_cast<LiveDepth*>(p)->same_input=same!=0;
    return 0;
}

static cudaError_t live_release(LiveDepth* c) {
    if (!c) return cudaSuccess;
    auto status=cudaStreamSynchronize(c->stream);
    for(auto event:c->events)if(event){auto e=cudaEventDestroy(event);if(status==cudaSuccess)status=e;}
    for(auto event:c->projection_events)if(event){auto e=cudaEventDestroy(event);if(status==cudaSuccess)status=e;}
    for (void* p : std::initializer_list<void*>{c->resized,c->sorted,c->smooth,c->guide,
        c->a,c->b,c->t0,c->t1,c->t2,c->t3,c->aligned,c->shift,
        static_cast<void*>(c->rgb),c->previous,c->output,c->motion,
        static_cast<void*>(c->owners),static_cast<void*>(c->bounds),
        static_cast<void*>(c->invalid),c->scratch,c->small_rgb,c->stereo_samples,c->window_state}) {
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
        C(cudaMalloc(&c->stereo_samples,32*32*sizeof(float)));
        C(cudaMalloc(&c->window_state,4*sizeof(float)));
        C(cudaMemsetAsync(c->window_state,0,4*sizeof(float),c->stream));
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
extern "C" __declspec(dllexport) int live_set_subpixel(void* p,int enabled) {
    if(!p || (enabled!=0 && enabled!=1))return 1;
    static_cast<LiveDepth*>(p)->subpixel=enabled!=0;return 0;
}
extern "C" __declspec(dllexport) int live_set_coverage(void* p,int enabled) {
    if(!p || (enabled!=0 && enabled!=1))return 1;
    static_cast<LiveDepth*>(p)->continuous_coverage=enabled!=0;return 0;
}
extern "C" __declspec(dllexport) int live_set_range_dt(void* p,double dt) {
    if(!p || !std::isfinite(dt) || (dt!=-1 && !(dt>0 && dt<=.1)))return 1;
    static_cast<LiveDepth*>(p)->range_dt=dt;return 0;
}
__global__ void sample_stereo_depth(LiveDepth c) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=1024)return;
    int x=min(((i%32)*2+1)*c.w/64,c.w-1),y=min(((i/32)*2+1)*c.h/64,c.h-1);
    c.stereo_samples[i]=c.aligned[y*c.w+x];
}
extern "C" __declspec(dllexport) int live_stereo_samples(void* p,float* output) {
    if(!p || !output)return 1;auto* c=static_cast<LiveDepth*>(p);
    sample_stereo_depth<<<4,256,0,c->stream>>>(*c);
    auto e=cudaGetLastError();if(e!=cudaSuccess)return int(e);
    e=cudaMemcpyAsync(output,c->stereo_samples,1024*sizeof(float),cudaMemcpyDeviceToHost,c->stream);
    if(e!=cudaSuccess)return int(e);
    return int(cudaStreamSynchronize(c->stream));
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
// Re-express the old range in current model units using stationary, unclipped
// depth anchors. Reject weak/contradictory fits; never smooth a global model
// scale/offset drift as if it were a scene's changing near/far extent.
__device__ bool transport_range(LiveDepth c,double& low,double& high) {
    double span=fmax(high-low,1e-6);
    __shared__ double sums[6][256],gain,offset;
    __shared__ int initial,accepted;
    int tid=threadIdx.x;
    if(tid==0){gain=1;offset=0;initial=0;accepted=1;}
    double a[4],b[4];bool valid[4];
    for(int q=0;q<4;q++) {
        int p=tid+q*256;
        int x=min(((p%32)*2+1)*c.w/64,c.w-1),y=min(((p/32)*2+1)*c.h/64,c.h-1);
        int i=y*c.w+x;a[q]=c.smooth[i];b[q]=(c.resized[i]-low)/span;
        bool changed=a[q]<=.05 || a[q]>=.95 || !isfinite(b[q]);
        for(int dy=-1;dy<=1 && !changed;dy++)for(int dx=-1;dx<=1 && !changed;dx++) {
            int j=min(max(y+dy,0),c.h-1)*c.w+min(max(x+dx,0),c.w-1);
            for(int k=0;k<3;k++)if(abs(int(c.rgb[j*3+k])-int(c.previous[j*3+k]))>4)changed=true;
        }
        valid[q]=!changed;
    }
    __syncthreads();
    for(int pass=0;pass<2;pass++) {
        double sx=0,sy=0,sxx=0,sxy=0,syy=0;int count=0;
        for(int q=0;q<4;q++) {
            if(!valid[q] || (pass && fabs(b[q]-(gain*a[q]+offset))>.025))continue;
            sx+=a[q];sy+=b[q];sxx+=a[q]*a[q];sxy+=a[q]*b[q];syy+=b[q]*b[q];++count;
        }
        sums[0][tid]=sx;sums[1][tid]=sy;sums[2][tid]=sxx;
        sums[3][tid]=sxy;sums[4][tid]=syy;sums[5][tid]=count;
        __syncthreads();
        for(int stride=128;stride;stride/=2) {
            if(tid<stride)for(int k=0;k<6;k++)sums[k][tid]+=sums[k][tid+stride];
            __syncthreads();
        }
        if(tid==0) {
            sx=sums[0][0];sy=sums[1][0];sxx=sums[2][0];sxy=sums[3][0];syy=sums[4][0];count=int(sums[5][0]);
            if(count<96 || (pass && count<initial*.8))accepted=0;
            if(accepted) {
                double variance=sxx-sx*sx/count;
                if(variance/count<.005)accepted=0;
                else {
                    gain=(sxy-sx*sy/count)/variance;offset=(sy-gain*sx)/count;
                    if(gain<.8 || gain>1.25 || fabs(offset)>.15)accepted=0;
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
__global__ void limits(LiveDepth c,double alpha,int reset) {
    const float* sorted=c.sorted;double* bounds=c.bounds;int n=c.n;double dt=c.range_dt;
    // Hold the already settled displayed range, including an affine-transported
    // range. Replacing it with raw percentiles here could move a stationary edge.
    if(c.same_input && !reset)return;
    if(dt>0 && !reset)transport_range(c,bounds[0],bounds[1]);
    if(threadIdx.x!=0)return;
    double target[2];
    for(int k=0;k<2;k++) {
        double pos=(n-1)*(k?.98:.02);int index=int(pos);double t=pos-index;
        float lo=sorted[index],hi=sorted[min(n-1,index+1)],diff=hi-lo;
        float value=float(t>=.5 ? double(hi)-double(diff)*(1-t) : double(lo)+double(diff)*t);
        target[k]=value;
    }
    if(dt>0 && !reset) {
        // Small range fluctuations settle slowly; substantial changes catch up.
        // One weight preserves endpoint ordering; cut/reset adopts current bounds.
        double span=fmax(fmax(bounds[1]-bounds[0],target[1]-target[0]),1e-6);
        double error=fmax(fabs(target[0]-bounds[0]),fabs(target[1]-bounds[1]))/span;
        double response=fmin(1.,fmax(0.,(error-.03)/.12));
        double tau=.15-.115*response;
        alpha=-expm1(-dt/tau);
    }
    for(int k=0;k<2;k++)bounds[k]=reset ? target[k] : alpha*target[k]+(1.-alpha)*bounds[k];
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
    if(!reset && !changed && delta<=threshold && !(c.same_input && delta<=static_depth_tolerance)) {
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
// Wider guide windows reuse sums within bounded 64-pixel chunks.
#ifndef SCREENTO3D_GUIDE_REFERENCE_ONLY
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
#include "guide_fixed.cuh"
#ifdef SCREENTO3D_GUIDE_TWO_THIRDS
#include "guide_reduced.cuh"
#endif
static cudaError_t live_guide(LiveDepth* c,int radius,cudaStream_t stream) {
#ifdef SCREENTO3D_FAST_GUIDE
    if(radius==12)return fixed_guide<12>(c,stream);
    if(radius==4)return fixed_guide<4>(c,stream);
#ifdef SCREENTO3D_GUIDE_TWO_THIRDS
    if(radius==8)return guide_two_thirds(c,stream);
#elif defined(SCREENTO3D_FIXED_GUIDE_8)
    if(radius==8)return fixed_guide<8>(c,stream);
#endif
#endif
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
#include "stereo_detail.cuh"

// Compression only, in fractions of one eye's width. Exact linear core and
// C1 soft knee; derivative stays in (0,1], so fixed-settings depth changes
// cannot be amplified. Fixed budgets avoid scene-statistic-driven pumping.
__device__ float budget_shift(float shift,int width) {
    float magnitude=fabsf(shift);
    float knee=width*(shift>=0?.0025f:.0035f)*.5f;
    float limit=width*(shift>=0?.006f:.008f)*.5f;
    if(magnitude<=knee)return shift;
    float excess=magnitude-knee,span=limit-knee;
    return copysignf(knee+span*(excess/(span+excess)),shift);
}
extern "C" __declspec(dllexport) int live_set_disparity_budget(void* handle,int enabled) {
    auto c=static_cast<LiveDepth*>(handle);
    if(!c||(enabled!=0&&enabled!=1))return 1;
    c->disparity_budget=enabled!=0;return 0;
}
// Explicit diagnostics only; normal rendering never reads the shift map back.
extern "C" __declspec(dllexport) int live_shift_snapshot(void* handle,float* output) {
    auto c=static_cast<LiveDepth*>(handle);if(!c||!output)return 1;
    auto e=cudaMemcpyAsync(output,c->shift,c->n*sizeof(float),cudaMemcpyDeviceToHost,c->stream);
    if(e!=cudaSuccess)return int(e);return int(cudaStreamSynchronize(c->stream));
}
__global__ void make_shift(LiveDepth c,float convergence,float scale) {
    // Forward destination shift for the LEFT eye; near inverse depth is crossed.
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    float left=0,right=0;
    if(i<c.n) {
        float s=(live_projection_depth(c)[i]-convergence)*scale*.5f;
        if(c.disparity_budget)s=budget_shift(s,c.w);
        if(c.detail_mode&1) {
            // Keep the original splat cells and visibility winners. A tiny
            // contour shift must not trigger a discrete owner/hole transition.
            float original=(c.aligned[i]-convergence)*scale*.5f;
            if(c.disparity_budget)original=budget_shift(original,c.w);
            float lo=floorf(original),hi=ceilf(original);
            s=lo==hi?original:fminf(fmaxf(s,fminf(original,lo+.0001f)),fmaxf(original,hi-.0001f));
        }
        c.shift[i]=s;
        if(c.window_dt>0 && s>0 && isfinite(s)) {
            int x=i%c.w;float disparity=fminf(2*s,c.w*.015f);
            if(x<s)left=disparity;
            if(c.w-1-x<s)right=disparity;
        }
    }
    if(c.window_dt>0) {
        for(int offset=16;offset;offset/=2) {
            left=fmaxf(left,__shfl_down_sync(0xffffffff,left,offset));
            right=fmaxf(right,__shfl_down_sync(0xffffffff,right,offset));
        }
        if((threadIdx.x&31)==0) {
            if(left>0)atomicMax(reinterpret_cast<unsigned*>(c.window_state),__float_as_uint(left));
            if(right>0)atomicMax(reinterpret_cast<unsigned*>(c.window_state+1),__float_as_uint(right));
        }
    }
}

__global__ void update_window(LiveDepth c) {
    for(int side=0;side<2;side++) {
        float target=c.window_state[side],old=c.window_state[side+2];
        // Immediate protection; source-time slow release avoids an oscillating border.
        float value=c.window_reset?target:fmaxf(target,old*float(exp(-c.window_dt/.20)));
        c.window_state[side+2]=value<.01f?0.f:value;
    }
}
static cudaError_t live_make_shift(LiveDepth* c,float convergence,float scale) {
    if(c->detail_mode&1) {
        contour_depth<<<(c->n+255)/256,256,0,c->stream>>>(*c);
        auto e=cudaGetLastError();if(e!=cudaSuccess)return e;
    }
    if(c->window_dt>0) {
        auto e=cudaMemsetAsync(c->window_state,0,2*sizeof(float),c->stream);if(e!=cudaSuccess)return e;
    }
    make_shift<<<(c->n+255)/256,256,0,c->stream>>>(*c,convergence,scale);
    auto e=cudaGetLastError();if(e!=cudaSuccess)return e;
    if(c->window_dt>0) {
        update_window<<<1,1,0,c->stream>>>(*c);c->window_reset=false;
    }
    return cudaGetLastError();
}
__global__ void mask_window(LiveDepth c,int eye,int band) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=band*c.h)return;
    int distance=i%band,x=eye?c.w-1-distance:distance,y=i/band;
    float weight=fminf(1.f,fmaxf(0.f,distance+1.f-c.window_state[eye+2]));
    if(weight>=1)return;
    for(int channel=0;channel<3;channel++) {
        auto& value=c.output[(y*c.w+x)*3+channel];
        value=(unsigned char)floorf(value*weight+.5f);
    }
}
static void live_mask_window(LiveDepth* c,int eye) {
    if(c->window_dt>0) {
        int band=int(ceilf(c->w*.015f));
        mask_window<<<(band*c->h+255)/256,256,0,c->stream>>>(*c,eye,band);
    }
}
extern "C" __declspec(dllexport) int live_set_window(void* handle,double dt,int reset) {
    auto c=static_cast<LiveDepth*>(handle);
    if(!c||!std::isfinite(dt)||(dt!=-1 && (dt<=0||dt>.1))||(reset!=0&&reset!=1))return 1;
    c->window_dt=dt;c->window_reset=reset!=0;return 0;
}
extern "C" __declspec(dllexport) int live_window_snapshot(void* handle,float* output) {
    auto c=static_cast<LiveDepth*>(handle);if(!c||!output)return 1;
    auto e=cudaMemcpyAsync(output,c->window_state,4*sizeof(float),cudaMemcpyDeviceToHost,c->stream);
    if(e!=cudaSuccess)return int(e);return int(cudaStreamSynchronize(c->stream));
}

// Reconstruct only already covered samples. Keep the existing near-surface
// owner and hole resolver; blend adjacent source colors on that same surface.
// Work is bounded to five source candidates per output, independent of disparity.
__global__ void reconstruct_subpixel(LiveDepth c) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n || !c.owners[i])return;
    int source=int(c.owners[i]&0xffffffffULL),row=(i/c.w)*c.w;
    const float* depth=c.aligned;
    float sum=0,r=0,g=0,b=0,z=depth[source];
    for(int offset=-2;offset<=2;offset++) {
        int j=source+offset;if(j<row || j>=row+c.w || fabsf(depth[j]-z)>.01f)continue;
        // Subtract integer coordinates first in coverage mode: adding a tiny
        // fractional shift to a large source coordinate can erase its fraction.
        float distance=c.continuous_coverage ? fabsf(float(i%c.w-j%c.w)-c.shift[j])
            : fabsf(float(i%c.w)-(float(j%c.w)+c.shift[j]));
        float w=fmaxf(0.f,1.f-distance);
        sum+=w;r+=w*c.rgb[j*3];g+=w*c.rgb[j*3+1];b+=w*c.rgb[j*3+2];
    }
    if(sum>1e-6f || c.continuous_coverage) {
        if(sum>0.f){r/=sum;g/=sum;b/=sum;}
        else {r=c.rgb[source*3];g=c.rgb[source*3+1];b=c.rgb[source*3+2];}
        // A near layer may cover only part of this destination pixel. The old
        // normalized color treated even tiny coverage as opaque. Preserve its
        // coverage and extend a locally visible farther surface into the rest.
        // Only a true source-depth discontinuity permits cross-surface blending;
        // full coverage, same-surface texture and unresolved holes are unchanged.
        if(c.continuous_coverage && sum<.99999f) {
            int direction=float(i%c.w-source%c.w)<c.shift[source] ? -1 : 1;
            for(int distance=1;distance<=2;distance++) {
                int j=source+direction*distance;
                if(j<row || j>=row+c.w)break;
                if(z-depth[j]>.04f) {
                    float coverage=fminf(1.f,sum),background=1.f-coverage;
                    float background_rgb[3]={float(c.rgb[j*3]),float(c.rgb[j*3+1]),float(c.rgb[j*3+2])};
                    if(c.detail_mode&2)sample_background(c,i,j,direction,background_rgb);
                    r=r*coverage+background_rgb[0]*background;
                    g=g*coverage+background_rgb[1]*background;
                    b=b*coverage+background_rgb[2]*background;
                    break;
                }
            }
        }
        c.output[i*3]=(unsigned char)fminf(255.f,floorf(r+.5f));
        c.output[i*3+1]=(unsigned char)fminf(255.f,floorf(g+.5f));
        c.output[i*3+2]=(unsigned char)fminf(255.f,floorf(b+.5f));
    }
}
static void live_reconstruct(LiveDepth* c) {
    if(c->subpixel)reconstruct_subpixel<<<(c->n+255)/256,256,0,c->stream>>>(*c);
    if(c->detail_mode&2)fill_background<<<(c->n+255)/256,256,0,c->stream>>>(*c);
}

// Both input adapters leave source-sized raw depth in c->resized on c->stream.
using LiveRangeUpdate = void(*)(LiveDepth*,double,int,const void*);
static int finish_live_depth(LiveDepth* c,int radius,double alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition,double pixel_alpha=-1.,
    LiveRangeUpdate range_update=nullptr,const void* range_parameters=nullptr) {
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[3],s));
    C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    if(range_update)range_update(c,alpha,reset,range_parameters);
    else limits<<<1,256,0,s>>>(*c,alpha,reset);
    C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    double temporal_weight=pixel_alpha<0. ? alpha : pixel_alpha;
    temporal<<<blocks,256,0,s>>>(*c,float(temporal_weight),float(1.0-temporal_weight),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));
#ifdef SCREENTO3D_GUIDE_REFERENCE_ONLY
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
#undef C
    return finish_live_depth(c,radius,alpha,color_threshold,depth_threshold,reset,diagnostic,transition);
}

extern "C" __declspec(dllexport) int live_post(void* handle,const unsigned char* rgb,
    const float* depth,int radius,double alpha,float ct,float dt,int reset,float* diagnostic,double transition) {
    return live_post_impl(handle,rgb,depth,radius,alpha,ct,dt,reset,diagnostic,transition,false);
}
extern "C" __declspec(dllexport) int live_post_gpu(void* handle,const unsigned char* rgb,
    const float* depth,int radius,double alpha,float ct,float dt,int reset,float* diagnostic,double transition) {
    return live_post_impl(handle,rgb,depth,radius,alpha,ct,dt,reset,diagnostic,transition,true);
}

// depth_on_device=1 requires the pointer to be produced on this exact stream.
static int live_post_source_impl(void* handle,const unsigned char* rgb,
    const float* depth,int depth_on_device,int radius,double alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition,double pixel_alpha=-1.,
    LiveRangeUpdate range_update=nullptr,const void* range_parameters=nullptr) {
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
#undef C
    return finish_live_depth(c,radius,alpha,color_threshold,depth_threshold,reset,diagnostic,transition,
                             pixel_alpha,range_update,range_parameters);
}
extern "C" __declspec(dllexport) int live_post_source(void* handle,const unsigned char* rgb,
    const float* depth,int depth_on_device,int radius,double alpha,float color_threshold,
    float depth_threshold,int reset,float* diagnostic,double transition) {
    return live_post_source_impl(handle,rgb,depth,depth_on_device,radius,alpha,color_threshold,
                                 depth_threshold,reset,diagnostic,transition);
}
extern "C" __declspec(dllexport) int live_project(void* handle,const float* refined,
    float convergence,float scale,int coverage,unsigned char* left,unsigned char* right,int* invalid) {
    auto c=(LiveDepth*)handle;if(!c || !left || !right || !invalid)return 1;
    auto s=c->stream;int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[7],s));
    if(refined)C(cudaMemcpyAsync(c->aligned,refined,c->n*4,cudaMemcpyHostToDevice,s));
    C(live_make_shift(c,convergence,scale));
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
        live_reconstruct(c);
        live_mask_window(c,eye);
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
