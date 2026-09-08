// Diagnostic-only subkernel timing for the current global-memory guide path.
#define live_create live_create_reference_export
#define live_destroy live_destroy_reference_export
#define live_post live_post_reference_export
#define live_post_source live_post_source_reference_export
#include "live_depth.cu"
#undef live_create
#undef live_destroy
#undef live_post
#undef live_post_source

#include <memory>
#include <unordered_map>

struct GuideProfile { cudaEvent_t events[5]={}; };
static std::unordered_map<void*,std::unique_ptr<GuideProfile>> profiles;

extern "C" __declspec(dllexport) int live_create(void** out,int w,int h,void* stream) {
    int status=live_create_reference_export(out,w,h,stream);if(status || !out || !*out)return status?status:1;
    std::unique_ptr<GuideProfile> profile;
    try {
        profile=std::make_unique<GuideProfile>();
        for(auto& event:profile->events) {
            auto e=cudaEventCreate(&event);
            if(e!=cudaSuccess) {
                for(auto old:profile->events)if(old)cudaEventDestroy(old);
                live_destroy_reference_export(*out);*out=nullptr;return int(e);
            }
        }
        profiles.emplace(*out,std::move(profile));return 0;
    } catch(...) {
        if(profile)for(auto event:profile->events)if(event)cudaEventDestroy(event);
        live_destroy_reference_export(*out);*out=nullptr;return int(cudaErrorMemoryAllocation);
    }
}
extern "C" __declspec(dllexport) int live_destroy(void* handle) {
    auto found=profiles.find(handle);if(found==profiles.end())return 1;
    int status=live_destroy_reference_export(handle);
    for(auto event:found->second->events) {
        auto e=cudaEventDestroy(event);if(!status && e!=cudaSuccess)status=int(e);
    }
    profiles.erase(found);return status;
}
extern "C" __declspec(dllexport) int live_post(void* handle,const unsigned char* rgb,
    const float* device_depth,int radius,double alpha,float color_threshold,float depth_threshold,int reset,
    float* diagnostic,double transition) {
    auto c=(LiveDepth*)handle;auto found=profiles.find(handle);
    if(!c || found==profiles.end() || !rgb || !device_depth || radius<1 || radius>12)return 1;
    auto s=c->stream;auto* timing=found->second.get();int blocks=(c->n+255)/256;
#define C(call) do {auto e=(call);if(e!=cudaSuccess){cudaStreamSynchronize(s);return int(e);}}while(0)
    C(cudaEventRecord(c->events[2],s));C(cudaMemcpyAsync(c->rgb,rgb,c->n*3,cudaMemcpyHostToDevice,s));
    C(cudaMemsetAsync(c->invalid,0,4,s));check_raw<<<(518*518+255)/256,256,0,s>>>(device_depth,c->invalid);
    resize_depth<<<blocks,256,0,s>>>(device_depth,c->resized,c->w,c->h,c->invalid);C(cudaGetLastError());
    C(cudaEventRecord(c->events[3],s));C(cub::DeviceRadixSort::SortKeys(c->scratch,c->scratch_bytes,c->resized,c->sorted,c->n,0,32,s));
    limits<<<1,1,0,s>>>(c->sorted,c->bounds,c->n,alpha,reset);C(cudaEventRecord(c->events[4],s));
    normalize_motion<<<blocks,256,0,s>>>(*c,color_threshold,reset);
    temporal<<<blocks,256,0,s>>>(*c,float(alpha),float(1.0-alpha),depth_threshold,float(transition),float(double(depth_threshold)-transition),reset);
    C(cudaEventRecord(c->events[5],s));C(cudaEventRecord(timing->events[0],s));
    moments_x<<<blocks,256,0,s>>>(*c,radius);C(cudaEventRecord(timing->events[1],s));
    coefficients<<<blocks,256,0,s>>>(*c,radius);C(cudaEventRecord(timing->events[2],s));
    coefficients_x<<<blocks,256,0,s>>>(*c,radius);C(cudaEventRecord(timing->events[3],s));
    guided<<<blocks,256,0,s>>>(*c,radius);C(cudaGetLastError());C(cudaEventRecord(timing->events[4],s));
    C(cudaEventRecord(c->events[6],s));C(cudaMemcpyAsync(c->previous,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,s));
    if(diagnostic)C(cudaMemcpyAsync(diagnostic,c->aligned,c->n*4,cudaMemcpyDeviceToHost,s));return 0;
#undef C
}
extern "C" __declspec(dllexport) int live_guide_times(void* handle,float* milliseconds) {
    auto found=profiles.find(handle);if(found==profiles.end() || !milliseconds)return 1;
    for(int i=0;i<4;i++) {
        auto e=cudaEventElapsedTime(milliseconds+i,found->second->events[i],found->second->events[i+1]);
        if(e!=cudaSuccess)return int(e);
    }
    return 0;
}
