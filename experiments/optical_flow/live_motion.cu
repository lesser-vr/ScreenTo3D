// Live-only, bounded one-frame depth history; no inference skipping.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cuda.h>
#include <nvOpticalFlowCuda.h>
#include <memory>
#include <stdexcept>
#include <string>
#include "../cuda_projection/live_depth.cu"

namespace {
thread_local std::string motion_error;
void cucheck(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
void ofcheck(NV_OF_STATUS e){if(e!=NV_OF_SUCCESS)throw std::runtime_error("NVOF status "+std::to_string(int(e)));}
using CreateApi=NV_OF_STATUS(NVOFAPI*)(uint32_t,NV_OF_CUDA_API_FUNCTION_LIST*);

__device__ float sample_f(const float* p,int w,int h,float x,float y) {
    x=fminf(w-1.f,fmaxf(0.f,x));y=fminf(h-1.f,fmaxf(0.f,y));
    int ix=int(x),iy=int(y),nx=min(ix+1,w-1),ny=min(iy+1,h-1);float fx=x-ix,fy=y-iy;
    return (p[iy*w+ix]*(1-fx)+p[iy*w+nx]*fx)*(1-fy)+(p[ny*w+ix]*(1-fx)+p[ny*w+nx]*fx)*fy;
}
__device__ float sample_rgb(const unsigned char* p,int w,int h,float x,float y,int channel) {
    x=fminf(w-1.f,fmaxf(0.f,x));y=fminf(h-1.f,fmaxf(0.f,y));
    int ix=int(x),iy=int(y),nx=min(ix+1,w-1),ny=min(iy+1,h-1);float fx=x-ix,fy=y-iy;
    return (p[(iy*w+ix)*3+channel]*(1-fx)+p[(iy*w+nx)*3+channel]*fx)*(1-fy)+
           (p[(ny*w+ix)*3+channel]*(1-fx)+p[(ny*w+nx)*3+channel]*fx)*fy;
}
__global__ void pack_motion(const unsigned char* rgb,int w,int h,unsigned char* dst,size_t pitch,int fw,int fh) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=fw*fh)return;
    int x=i%fw,y=i/fw;float sx=(x+.5f)*w/fw-.5f,sy=(y+.5f)*h/fh-.5f;
    auto* pixel=dst+y*pitch+x*4;
    for(int c=0;c<3;c++)pixel[c]=(unsigned char)fminf(255.f,fmaxf(0.f,sample_rgb(rgb,w,h,sx,sy,c)+.5f));
    pixel[3]=255;
}
__device__ float2 sample_flow(const unsigned char* p,size_t pitch,int w,int h,float x,float y) {
    x=fminf(w-1.f,fmaxf(0.f,(x+.5f)/2-.5f));y=fminf(h-1.f,fmaxf(0.f,(y+.5f)/2-.5f));
    int ix=int(x),iy=int(y),nx=min(ix+1,w-1),ny=min(iy+1,h-1);float fx=x-ix,fy=y-iy;
    auto a=reinterpret_cast<const short2*>(p+iy*pitch)[ix];auto b=reinterpret_cast<const short2*>(p+iy*pitch)[nx];
    auto c=reinterpret_cast<const short2*>(p+ny*pitch)[ix];auto d=reinterpret_cast<const short2*>(p+ny*pitch)[nx];
    return make_float2(((a.x*(1-fx)+b.x*fx)*(1-fy)+(c.x*(1-fx)+d.x*fx)*fy)/32.f,
                       ((a.y*(1-fx)+b.y*fx)*(1-fy)+(c.y*(1-fx)+d.y*fx)*fy)/32.f);
}
__global__ void blend_motion(LiveDepth c,const float* current,const float* previous,
    const unsigned char* previous_rgb,const unsigned char* backward,size_t bp,
    const unsigned char* forward,size_t fp,int fw,int fh,float age_weight,unsigned char* accepted) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.n)return;
    if(accepted)accepted[i]=0;
    int x=i%c.w,y=i/c.w;float value=current[i];
    if(x<2||y<2||x>=c.w-2||y>=c.h-2)return;
    float gx=(x+.5f)*fw/c.w-.5f,gy=(y+.5f)*fh/c.h-.5f;
    float2 back=sample_flow(backward,bp,(fw+1)/2,(fh+1)/2,gx,gy);
    float sx=x+back.x*c.w/fw,sy=y+back.y*c.h/fh;
    if(sx<2||sy<2||sx>=c.w-2||sy>=c.h-2)return;
    if(back.x*back.x+back.y*back.y<.04f)return; // static depth already has its own EMA
    float2 reverse=sample_flow(forward,fp,(fw+1)/2,(fh+1)/2,gx+back.x,gy+back.y);
    float fb=hypotf(back.x+reverse.x,back.y+reverse.y);
    if(fb>=.75f)return;
    float old=sample_f(previous,c.w,c.h,sx,sy),delta=fabsf(value-old);
    if(!isfinite(old)||delta>=.06f)return;
    float photo=0,lo=value,hi=value,old_lo=old,old_hi=old;
    for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
        float a=current[(y+dy)*c.w+x+dx],b=sample_f(previous,c.w,c.h,sx+dx,sy+dy);
        lo=fminf(lo,a);hi=fmaxf(hi,a);old_lo=fminf(old_lo,b);old_hi=fmaxf(old_hi,b);
        for(int k=0;k<3;k++)photo=fmaxf(photo,fabsf(c.rgb[((y+dy)*c.w+x+dx)*3+k]-sample_rgb(previous_rgb,c.w,c.h,sx+dx,sy+dy,k))/255.f);
    }
    if(photo>=.06f || hi-lo>=.04f || old_hi-old_lo>=.04f)return;
    // Reject interpolation across an old silhouette even if its blended value fits.
    int ix=int(sx),iy=int(sy);float a=previous[iy*c.w+ix],b=previous[iy*c.w+ix+1],d=previous[(iy+1)*c.w+ix],e=previous[(iy+1)*c.w+ix+1];
    if(fmaxf(fmaxf(a,b),fmaxf(d,e))-fminf(fminf(a,b),fminf(d,e))>=.04f)return;
    float weight=age_weight*(1-fb/.75f)*(1-photo/.06f)*(1-delta/.06f);
    float step=fminf(.012f,fmaxf(-.012f,weight*(old-value)));
    c.aligned[i]=value+step;
    if(accepted)accepted[i]=1;
}

struct Motion {
    int w,h,fw,fh,device;DWORD owner=GetCurrentThreadId();cudaStream_t stream=nullptr;
    HMODULE library=nullptr;NV_OF_CUDA_API_FUNCTION_LIST api{};NvOFHandle session=nullptr;
    NvOFGPUBufferHandle input[2]{},flow[2]{};unsigned char* ip[2]{},*op[2]{};
    size_t istride[2]{},ostride[2]{};float* depth[2]{};unsigned char* previous_rgb=nullptr,*accepted=nullptr;
    int current=0;bool primed=false,poisoned=false;
    double* static_snapshot=nullptr; // Two range bounds followed by w*h floats.
    void check() {
        int d=-1;cucheck(cudaGetDevice(&d));
        if(owner!=GetCurrentThreadId()||device!=d||poisoned)throw std::runtime_error("Invalid motion owner/device/session");
    }
    void close() {
        std::string failure;
        auto cuda_release=[&](cudaError_t e){if(e!=cudaSuccess&&failure.empty())failure=cudaGetErrorString(e);};
        auto of_release=[&](NV_OF_STATUS e){if(e!=NV_OF_SUCCESS&&failure.empty())failure="NVOF release failed";};
        if(stream)cuda_release(cudaStreamSynchronize(stream));
        for(auto& b:input)if(b){of_release(api.nvOFDestroyGPUBufferCuda(b));b=nullptr;}
        for(auto& b:flow)if(b){of_release(api.nvOFDestroyGPUBufferCuda(b));b=nullptr;}
        if(session){of_release(api.nvOFDestroy(session));session=nullptr;}
        for(auto& p:depth)if(p){cuda_release(cudaFree(p));p=nullptr;}
        if(static_snapshot){cuda_release(cudaFree(static_snapshot));static_snapshot=nullptr;}
        if(previous_rgb){cuda_release(cudaFree(previous_rgb));previous_rgb=nullptr;}
        if(accepted){cuda_release(cudaFree(accepted));accepted=nullptr;}
        if(library){FreeLibrary(library);library=nullptr;}
        stream=nullptr;
        if(!failure.empty())throw std::runtime_error(failure);
    }
    ~Motion(){try{close();}catch(...) {}}
    void init(int width,int height,void* borrowed,int diagnostic) {
        if(width<16||width>4096||height<16||height>2160||!borrowed||(diagnostic!=0&&diagnostic!=1))throw std::runtime_error("Invalid motion dimensions/stream");
        w=width;h=height;stream=static_cast<cudaStream_t>(borrowed);cucheck(cudaGetDevice(&device));
        double scale=fmin(1.,640./std::max(w,h));
        fw=std::max(32,int(std::round(w*scale/2))*2);fh=std::max(32,int(std::round(h*scale/2))*2);
        CUcontext context=nullptr;if(cuCtxGetCurrent(&context)!=CUDA_SUCCESS||!context)throw std::runtime_error("No engine CUDA context");
        library=LoadLibraryExW(L"nvofapi64.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
        if(!library)throw std::runtime_error("NVIDIA optical flow driver unavailable");
        auto create=reinterpret_cast<CreateApi>(GetProcAddress(library,"NvOFAPICreateInstanceCuda"));
        if(!create)throw std::runtime_error("NVIDIA optical flow API unavailable");ofcheck(create(NV_OF_API_VERSION,&api));
        if(!api.nvCreateOpticalFlowCuda||!api.nvOFSetIOCudaStreams||!api.nvOFInit||!api.nvOFCreateGPUBufferCuda||
           !api.nvOFGPUBufferGetCUdeviceptr||!api.nvOFGPUBufferGetStrideInfo||!api.nvOFExecute||!api.nvOFDestroyGPUBufferCuda||!api.nvOFDestroy)
            throw std::runtime_error("Incomplete optical flow API");
        ofcheck(api.nvCreateOpticalFlowCuda(context,&session));
        ofcheck(api.nvOFSetIOCudaStreams(session,reinterpret_cast<CUstream>(stream),reinterpret_cast<CUstream>(stream)));
        NV_OF_INIT_PARAMS init{};init.width=fw;init.height=fh;init.outGridSize=NV_OF_OUTPUT_VECTOR_GRID_SIZE_2;
        init.hintGridSize=NV_OF_HINT_VECTOR_GRID_SIZE_2;init.mode=NV_OF_MODE_OPTICALFLOW;init.perfLevel=NV_OF_PERF_LEVEL_FAST;
        ofcheck(api.nvOFInit(session,&init));
        for(int k=0;k<2;k++) {
            NV_OF_BUFFER_DESCRIPTOR desc{};desc.width=fw;desc.height=fh;desc.bufferUsage=NV_OF_BUFFER_USAGE_INPUT;desc.bufferFormat=NV_OF_BUFFER_FORMAT_ABGR8;
            ofcheck(api.nvOFCreateGPUBufferCuda(session,&desc,NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR,&input[k]));
            desc.width=(fw+1)/2;desc.height=(fh+1)/2;desc.bufferUsage=NV_OF_BUFFER_USAGE_OUTPUT;desc.bufferFormat=NV_OF_BUFFER_FORMAT_SHORT2;
            ofcheck(api.nvOFCreateGPUBufferCuda(session,&desc,NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR,&flow[k]));
            ip[k]=reinterpret_cast<unsigned char*>(api.nvOFGPUBufferGetCUdeviceptr(input[k]));
            op[k]=reinterpret_cast<unsigned char*>(api.nvOFGPUBufferGetCUdeviceptr(flow[k]));
            NV_OF_CUDA_BUFFER_STRIDE_INFO stride{};ofcheck(api.nvOFGPUBufferGetStrideInfo(input[k],&stride));
            if(stride.numPlanes!=1)throw std::runtime_error("Invalid input plane count");istride[k]=stride.strideInfo[0].strideXInBytes;
            ofcheck(api.nvOFGPUBufferGetStrideInfo(flow[k],&stride));
            if(stride.numPlanes!=1)throw std::runtime_error("Invalid flow plane count");ostride[k]=stride.strideInfo[0].strideXInBytes;
            if(!ip[k]||!op[k]||istride[k]<size_t(fw)*4||ostride[k]<size_t((fw+1)/2)*4)throw std::runtime_error("Invalid motion buffer pitch");
            cucheck(cudaMalloc(&depth[k],size_t(w)*h*sizeof(float)));
        }
        cucheck(cudaMalloc(&previous_rgb,size_t(w)*h*3));
        if(diagnostic)cucheck(cudaMalloc(&accepted,size_t(w)*h));
    }
    void apply(LiveDepth* c,bool reset,double dt) {
        check();if(!c||c->w!=w||c->h!=h||c->stream!=stream||!std::isfinite(dt)||dt<=0||dt>.1)throw std::runtime_error("Invalid motion frame contract");
        try {
            pack_motion<<<(fw*fh+255)/256,256,0,stream>>>(c->rgb,w,h,ip[current],istride[current],fw,fh);cucheck(cudaGetLastError());
            cucheck(cudaMemcpyAsync(depth[current],c->aligned,size_t(w)*h*4,cudaMemcpyDeviceToDevice,stream));
            if(accepted)cucheck(cudaMemsetAsync(accepted,0,size_t(w)*h,stream));
            if(primed&&!reset) {
                for(int direction=0;direction<2;direction++) {
                    NV_OF_EXECUTE_INPUT_PARAMS in{};NV_OF_EXECUTE_OUTPUT_PARAMS out{};
                    in.inputFrame=input[direction?current^1:current];in.referenceFrame=input[direction?current:current^1];
                    in.disableTemporalHints=NV_OF_TRUE;out.outputBuffer=flow[direction];
                    ofcheck(api.nvOFExecute(session,&in,&out));
                }
                blend_motion<<<(w*h+255)/256,256,0,stream>>>(*c,depth[current],depth[current^1],previous_rgb,
                    op[0],ostride[0],op[1],ostride[1],fw,fh,float(.45*std::exp(-dt/.1)),accepted);cucheck(cudaGetLastError());
            }
            cucheck(cudaMemcpyAsync(previous_rgb,c->rgb,size_t(w)*h*3,cudaMemcpyDeviceToDevice,stream));
            current^=1;primed=true;
        } catch(...) {poisoned=true;throw;}
    }
};

// Called only after a completed native render, on its owner stream. The guide
// scratch word is dead until the next postprocess. No texture lease is touched.
__global__ void static_depth_probe(LiveDepth c,double* snapshot,bool compare,int* changed) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i>=c.n)return;
    float final_depth=c.aligned[i];
    float* last=reinterpret_cast<float*>(snapshot+2);
    int pending=(!isfinite(final_depth) || fabsf(c.smooth[i]-c.resized[i])>static_depth_tolerance)?1:0;
    if(compare && last[i]!=final_depth)pending|=2;
    last[i]=final_depth;
    if(i<2) {
        double span=fmax(c.bounds[1]-c.bounds[0],1e-6);
        if(!compare || fabs(c.bounds[i]-snapshot[i])>2e-7*span)pending|=4;
        snapshot[i]=c.bounds[i];
        float target=c.window_state[i];
        if(c.window_state[i+2]!=(target<.01f?0.f:target))pending|=8;
    }
    unsigned active=__activemask();
#if __CUDA_ARCH__ >= 800
    int mask=__reduce_or_sync(active,pending);
#else
    int mask=0;
    for(int bit=1;bit<=8;bit<<=1)
        if(__any_sync(active,pending&bit))mask|=bit;
#endif
    if(mask && (threadIdx.x&31)==0)atomicOr(changed,mask);
}
}
extern "C" __declspec(dllexport) int motion_static_probe(void* p,void* live,int compare,int* pending) {
    try {
        auto m=static_cast<Motion*>(p);auto c=static_cast<LiveDepth*>(live);
        if(!m||!c||!pending||m->w!=c->w||m->h!=c->h||m->stream!=c->stream)
            throw std::runtime_error("Invalid static probe descriptor");
        m->check();
        if(!m->static_snapshot){
            cucheck(cudaMalloc(&m->static_snapshot,2*sizeof(double)+size_t(c->n)*sizeof(float)));
            compare=0;
        }
        int* flag=reinterpret_cast<int*>(c->t3);
        cucheck(cudaMemsetAsync(flag,0,sizeof(int),m->stream));
        static_depth_probe<<<(c->n+255)/256,256,0,m->stream>>>(*c,m->static_snapshot,compare!=0,flag);
        cucheck(cudaGetLastError());
        int changed=0;
        cucheck(cudaMemcpyAsync(&changed,flag,sizeof(int),cudaMemcpyDeviceToHost,m->stream));
        cucheck(cudaStreamSynchronize(m->stream));
        *pending=changed | (compare?0:16);
        return 1;
    } catch(const std::exception& e){motion_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) const char* motion_last_error(){return motion_error.c_str();}
extern "C" __declspec(dllexport) void* motion_create(int w,int h,void* stream,int diagnostic) {
    try{auto p=std::make_unique<Motion>();p->init(w,h,stream,diagnostic);return p.release();}
    catch(const std::exception& e){motion_error=e.what();return nullptr;}
}
extern "C" __declspec(dllexport) int motion_apply(void* p,void* live,int reset,double dt) {
    try{if(!p||(reset!=0&&reset!=1))throw std::runtime_error("Invalid motion handle/reset");static_cast<Motion*>(p)->apply(static_cast<LiveDepth*>(live),reset!=0,dt);return 1;}
    catch(const std::exception& e){motion_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int motion_destroy(void* p) {
    try{auto c=static_cast<Motion*>(p);if(c){int device=-1;cucheck(cudaGetDevice(&device));
        if(c->owner!=GetCurrentThreadId()||c->device!=device)throw std::runtime_error("Foreign motion owner/device");
        std::unique_ptr<Motion> owned(c);c->close();}return 1;}
    catch(const std::exception& e){motion_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int motion_readback(void* p,float* unfiltered,unsigned char* accepted) {
    try{auto c=static_cast<Motion*>(p);if(!c||!c->primed||!c->accepted||!unfiltered||!accepted)throw std::runtime_error("Not a primed diagnostic motion session");c->check();
        cucheck(cudaMemcpyAsync(unfiltered,c->depth[c->current^1],size_t(c->w)*c->h*4,cudaMemcpyDeviceToHost,c->stream));
        cucheck(cudaMemcpyAsync(accepted,c->accepted,size_t(c->w)*c->h,cudaMemcpyDeviceToHost,c->stream));
        cucheck(cudaStreamSynchronize(c->stream));return 1;}
    catch(const std::exception& e){motion_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int motion_depth(void* p,void* live,float* output) {
    try{auto m=static_cast<Motion*>(p);auto c=static_cast<LiveDepth*>(live);
        if(!m||!m->primed||!c||!output||c->w!=m->w||c->h!=m->h||c->stream!=m->stream)throw std::runtime_error("Invalid diagnostic depth descriptor");m->check();
        cucheck(cudaMemcpyAsync(output,c->aligned,size_t(c->n)*4,cudaMemcpyDeviceToHost,m->stream));
        cucheck(cudaStreamSynchronize(m->stream));return 1;}
    catch(const std::exception& e){motion_error=e.what();return 0;}
}
