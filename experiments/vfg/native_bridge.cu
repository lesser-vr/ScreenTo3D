// Experiment-only bridge. Borrow the pinned LiveDepth layout and CUDA stream.
#include "../cuda_projection/live_texture_runtime.cu"
#include "nvVideoEffects.h"
#include "nvVFXVideoFrameGeneration.h"
char* g_nvVFXSDKPath = nullptr;

static void vcheck(NvCV_Status status) {
    if(status!=NVCV_SUCCESS)throw std::runtime_error("VFG status "+std::to_string(status));
}
struct VfgSession {
    int w,h; DWORD owner=GetCurrentThreadId(); cudaStream_t stream;
    NvVFX_Handle effect=nullptr;
    NvCVImage prev,curr,dst;
    VfgSession(int width,int height,void* borrowed):w(width),h(height),stream(static_cast<cudaStream_t>(borrowed)) {
        if(w<32 || w>8192 || h<16 || h>2160 || !stream)throw std::runtime_error("Invalid VFG dimensions/stream");
        try {
            vcheck(NvVFX_CreateEffect(NVVFX_FX_VIDEO_FRAME_GENERATION,&effect));
            vcheck(NvVFX_SetCudaStream(effect,NVVFX_CUDA_STREAM,stream));
            vcheck(NvVFX_SetU32(effect,NVVFX_INPUT_WIDTH,w));
            vcheck(NvVFX_SetU32(effect,NVVFX_INPUT_HEIGHT,h));
            vcheck(NvVFX_SetU32(effect,NVVFXVIDEOFRAMEGENERATION_MODE,NVVFXVIDEOFRAMEGENERATION_MODE_MEDIUM));
            vcheck(NvVFX_SetU32(effect,NVVFXVIDEOFRAMEGENERATION_AUTOMATIC_SHOT_CHANGE_DETECTION_ENABLED,0));
            vcheck(NvVFX_Load(effect));
            vcheck(NvVFX_SetU32(effect,NVVFXVIDEOFRAMEGENERATION_FRAME_MULTIPLIER,2));
        } catch(...) { if(effect)NvVFX_DestroyEffect(effect); effect=nullptr; throw; }
    }
    void check(){if(owner!=GetCurrentThreadId())throw std::runtime_error("Foreign VFG owner thread");}
    ~VfgSession(){cudaStreamSynchronize(stream);if(effect)NvVFX_DestroyEffect(effect);}
};
extern "C" __declspec(dllexport) void* vfg_create(int w,int h,void* stream) {
    try{return new VfgSession(w,h,stream);}catch(const std::exception& e){projection_texture_error=e.what();return nullptr;}
}
extern "C" __declspec(dllexport) int vfg_destroy(void* value) {
    try{auto* c=static_cast<VfgSession*>(value);if(c){c->check();CU(cudaStreamSynchronize(c->stream));delete c;}return 1;}
    catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int vfg_run(void* value,void* previous,void* current,void* output) {
    try {
        auto* c=static_cast<VfgSession*>(value);if(!c || !previous || !current || !output || previous==current || output==current || output==previous)
            throw std::runtime_error("Invalid VFG buffers");
        c->check();
        vcheck(NvCVImage_Init(&c->prev,c->w,c->h,c->w*4,previous,NVCV_RGBA,NVCV_U8,NVCV_INTERLEAVED,NVCV_GPU));
        vcheck(NvCVImage_Init(&c->curr,c->w,c->h,c->w*4,current,NVCV_RGBA,NVCV_U8,NVCV_INTERLEAVED,NVCV_GPU));
        vcheck(NvCVImage_Init(&c->dst,c->w,c->h,c->w*4,output,NVCV_RGBA,NVCV_U8,NVCV_INTERLEAVED,NVCV_GPU));
        vcheck(NvVFX_SetImage(c->effect,NVVFX_INPUT_IMAGE_0,&c->prev));
        vcheck(NvVFX_SetImage(c->effect,NVVFX_INPUT_IMAGE_1,&c->curr));
        vcheck(NvVFX_SetImage(c->effect,NVVFX_OUTPUT_IMAGE,&c->dst));
        vcheck(NvVFX_SetU32(c->effect,NVVFXVIDEOFRAMEGENERATION_SHOT_CHANGE,0));
        vcheck(NvVFX_SetU32(c->effect,NVVFXVIDEOFRAMEGENERATION_FRAME_INDEX,1));
        vcheck(NvVFX_Run(c->effect,0));CU(cudaStreamSynchronize(c->stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int vfg_window_capture(void* live,float* output) {
    try {
        auto* c=static_cast<LiveDepth*>(live);if(!c||!output)throw std::runtime_error("Invalid window snapshot");
        if(c->window_dt>0)CU(cudaMemcpyAsync(output,c->window_state+2,2*sizeof(float),cudaMemcpyDeviceToDevice,c->stream));
        else CU(cudaMemsetAsync(output,0,2*sizeof(float),c->stream));
        return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
__global__ void vfg_window_mask(uchar4* pixels,int width,int height,const float* previous,const float* current) {
    int eye_width=width/2,band=int(ceilf(eye_width*.015f));
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=band*height*2)return;
    int eye=i/(band*height),local=i%(band*height),distance=local%band,y=local/band;
    int x=eye?width-1-distance:distance;
    float amount=fminf(eye_width*.015f,fmaxf(previous[eye],current[eye]));
    float weight=fminf(1.f,fmaxf(0.f,distance+1.f-amount));
    if(weight>=1)return;
    auto& p=pixels[y*width+x];
    p.x=(unsigned char)floorf(p.x*weight+.5f);p.y=(unsigned char)floorf(p.y*weight+.5f);
    p.z=(unsigned char)floorf(p.z*weight+.5f);p.w=255;
}
extern "C" __declspec(dllexport) int vfg_window_apply(void* value,void* output,const float* previous,const float* current) {
    try {
        auto* c=static_cast<VfgSession*>(value);
        if(!c||!output||!previous||!current)throw std::runtime_error("Invalid generated window buffers");c->check();
        int n=int(ceilf(c->w/2*.015f))*c->h*2;
        vfg_window_mask<<<(n+255)/256,256,0,c->stream>>>(static_cast<uchar4*>(output),c->w,c->h,previous,current);
        CU(cudaGetLastError());CU(cudaStreamSynchronize(c->stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
__global__ void vfg_pack_eye(const unsigned char* rgb,uchar4* rgba,int w,int h,int eye) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h)return;
    rgba[(i/w)*(w*2)+(i%w)+eye*w]=make_uchar4(rgb[i*3],rgb[i*3+1],rgb[i*3+2],255);
}
extern "C" __declspec(dllexport) int vfg_project(void* live,void* rgba,float convergence,float scale,int coverage,const float* refined) {
    try {
        auto* c=static_cast<LiveDepth*>(live);
        if(!c || !rgba || !std::isfinite(convergence) || !std::isfinite(scale) || scale<0 || (coverage!=0 && coverage!=1))
            throw std::runtime_error("Invalid VFG projection input");
        auto stream=c->stream;int blocks=(c->n+255)/256,invalid=0;
        CU(cudaEventRecord(c->events[7],stream));
        CU(cudaMemcpyAsync(&invalid,c->invalid,4,cudaMemcpyDeviceToHost,stream));CU(cudaStreamSynchronize(stream));
        if(invalid)throw std::runtime_error("Nonfinite VFG projection depth");
        if(refined)CU(cudaMemcpyAsync(c->aligned,refined,c->n*4,cudaMemcpyHostToDevice,stream));
        CU(live_make_shift(c,convergence,scale));
        CU(cudaEventRecord(c->projection_events[0],stream));
        for(int eye=0;eye<2;++eye){
            if(eye)negate_shift<<<blocks,256,0,stream>>>(c->shift,c->n);
            CU(cudaMemsetAsync(c->owners,0,c->n*8,stream));
            splat<<<blocks,256,0,stream>>>(c->aligned,c->shift,c->owners,c->w,c->n,coverage!=0);
            CU(cudaEventRecord(c->projection_events[eye*3+1],stream));
            if(c->parallel_resolve)launch_resolve_parallel(c->rgb,c->owners,c->output,c->w,c->h,stream);
            else resolve<<<(c->h+63)/64,64,0,stream>>>(c->rgb,c->owners,c->output,c->w,c->h);
            live_reconstruct(c);
            live_mask_window(c,eye);
            CU(cudaEventRecord(c->projection_events[eye*3+2],stream));
            vfg_pack_eye<<<blocks,256,0,stream>>>(c->output,static_cast<uchar4*>(rgba),c->w,c->h,eye);
            CU(cudaEventRecord(c->projection_events[eye*3+3],stream));
        }
        CU(cudaGetLastError());CU(cudaEventRecord(c->events[8],stream));CU(cudaStreamSynchronize(stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
__global__ void vfg_to_surface(const uchar4* rgba,cudaSurfaceObject_t surface,int w,int h){
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<w*h)surf2Dwrite(rgba[i],surface,(i%w)*4,i/w);
}
extern "C" __declspec(dllexport) int vfg_publish(void* value,void* rgba,int w,int h,int index,void* borrowed){
    try {
        auto* pool=static_cast<OwnedTexturePool*>(value);
        if(!pool || !rgba || !borrowed || index<0 || index>1)throw std::runtime_error("Invalid VFG publication");
        auto* texture=pool->texture.get();texture->check();
        if(w!=texture->w*2 || h!=texture->h)throw std::runtime_error("VFG pool shape mismatch");
        auto stream=static_cast<cudaStream_t>(borrowed);auto& slot=texture->slots[index];
        cudaExternalSemaphoreWaitParams wait={};wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        for(int eye=0;eye<2;eye++)
            pack_eye_surface<<<(w*h/2+255)/256,256,0,stream>>>(
                static_cast<unsigned char*>(rgba)+eye*(w/2)*4,slot.surface,w/2,h,eye,texture->layout,w,4);
        CU(cudaGetLastError());cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));CU(cudaStreamSynchronize(stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
