// Isolated quality experiment. Production binaries and borrowed LiveDepth ABI stay intact.
#define live_pool_publish baseline_pool_publish
#define live_pool_destroy baseline_pool_destroy
#include "live_texture_runtime.cu"
#undef live_pool_publish
#undef live_pool_destroy
extern "C" __declspec(dllexport) int half_trial_publish(void* value,void* live,
    float convergence,float scale,int coverage,const float* refined,int index,int clear,int edge_aware) {
    try {
        auto* pool=static_cast<OwnedTexturePool*>(value);
        if(!pool)throw std::runtime_error("Missing Half render pool");
        auto* texture=pool->texture.get();texture->check();
        auto* full=static_cast<LiveDepth*>(live);
        if(!full || full->w!=texture->w || full->h!=texture->h ||
           (texture->layout!=1 && texture->layout!=3) || index<0 || index>1 ||
           !std::isfinite(convergence) || !std::isfinite(scale) || scale<0 ||
           (coverage!=0 && coverage!=1) || (clear!=0 && clear!=1) ||
           (edge_aware!=0 && edge_aware!=1))
            throw std::runtime_error("Invalid Half render descriptor");
        if(clear)return baseline_pool_publish(value,live,convergence,scale,coverage,refined,index,clear);
        return publish_reduced_half(texture,full,convergence,scale,coverage,refined,index,edge_aware);
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}

extern "C" __declspec(dllexport) int live_pool_publish(void* value,void* live,
    float convergence,float scale,int coverage,const float* refined,int index,int clear) {
    return half_trial_publish(value,live,convergence,scale,coverage,refined,index,clear,1);
}

extern "C" __declspec(dllexport) int live_pool_destroy(void* value) {
    return baseline_pool_destroy(value);
}