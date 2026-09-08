#define DEPTHSBS_TEXTURE_TIMING
#include "live_texture_pool.cu"

// Synthetic integration-test producer; never selected by the live worker.
extern "C" __declspec(dllexport) int live_pool_paint(void* value,int index,int frame,int clear) {
    try {
        auto* pool=static_cast<OwnedTexturePool*>(value);
        if(!pool || index<0 || index>1 || frame<0 || (clear!=0 && clear!=1))
            throw std::runtime_error("Invalid synthetic pool descriptor");
        auto* texture=pool->texture.get();texture->check();auto& slot=texture->slots[index];
        cudaExternalSemaphoreWaitParams wait={};wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,nullptr));
        paint<<<dim3((texture->w*2+31)/32,(texture->h+7)/8),dim3(32,8)>>>(slot.surface,texture->w*2,texture->h,frame,clear!=0);
        CU(cudaGetLastError());cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,nullptr));
        CU(cudaStreamSynchronize(nullptr));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
