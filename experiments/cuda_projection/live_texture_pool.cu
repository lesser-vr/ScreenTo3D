// Experimental worker-owned pool. No handle is duplicated into another process
// here: the owned GUI imports it after validating its multiprocessing child PID.
// Old diagnostic DLLs remain pinned and unchanged on disk.
#include "live_texture_publish.cu"
#include <memory>

struct OwnedTexturePool {
    std::unique_ptr<ProjectionTexture> texture;
    HANDLE handles[2]={};
    LUID luid={};
    OwnedTexturePool(int width,int height,bool diagnostic) {
        texture=std::make_unique<ProjectionTexture>(width,height,diagnostic);
        try {
            for(int i=0;i<2;i++) {
                ComPtr<IDXGIResource1> resource;
                hr(texture->slots[i].writer.As(&resource),"Pool resource");
                hr(resource->CreateSharedHandle(nullptr,
                    DXGI_SHARED_RESOURCE_READ|DXGI_SHARED_RESOURCE_WRITE,
                    nullptr,&handles[i]),"Pool local handle");
            }
            ComPtr<IDXGIDevice> dxgi;hr(texture->producer.As(&dxgi),"Pool DXGI");
            ComPtr<IDXGIAdapter> adapter;hr(dxgi->GetAdapter(&adapter),"Pool adapter");
            DXGI_ADAPTER_DESC desc={};hr(adapter->GetDesc(&desc),"Pool adapter desc");
            luid=desc.AdapterLuid;
        } catch(...) {
            close_handles();throw;
        }
    }
    void close_handles() noexcept {
        for(auto& handle:handles)if(handle){CloseHandle(handle);handle=nullptr;}
    }
    ~OwnedTexturePool(){close_handles();}
};

extern "C" __declspec(dllexport) void* live_pool_create(int w,int h,int diagnostic) {
    try {
        if(diagnostic!=0 && diagnostic!=1)throw std::runtime_error("Invalid pool diagnostic flag");
        return new OwnedTexturePool(w,h,diagnostic!=0);
    }catch(const std::exception& e){projection_texture_error=e.what();return nullptr;}
}
extern "C" __declspec(dllexport) int live_pool_descriptor(void* value,
    unsigned long long* handles,unsigned long* low,long* high,unsigned long* pid) {
    try {
        auto* pool=static_cast<OwnedTexturePool*>(value);
        if(!pool || !handles || !low || !high || !pid)throw std::runtime_error("Missing pool descriptor");
        pool->texture->check();
        for(int i=0;i<2;i++)handles[i]=reinterpret_cast<unsigned long long>(pool->handles[i]);
        *low=pool->luid.LowPart;*high=pool->luid.HighPart;*pid=GetCurrentProcessId();return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int live_pool_publish(void* value,void* live,
    float convergence,float scale,int coverage,const float* refined,int index,int clear) {
    if(!value){projection_texture_error="Missing pool";return 0;}
    auto* pool=static_cast<OwnedTexturePool*>(value);
    return live_texture_publish(pool->texture.get(),live,convergence,scale,coverage,refined,index,clear);
}
extern "C" __declspec(dllexport) int live_pool_readback(void* value,int index,unsigned char* output) {
    if(!value){projection_texture_error="Missing pool";return 0;}
    auto* pool=static_cast<OwnedTexturePool*>(value);
    if(index<0 || index>1 || !pool->texture->slots[index].staging){
        projection_texture_error="Diagnostic staging is disabled";return 0;
    }
    return live_texture_readback(pool->texture.get(),index,output);
}
extern "C" __declspec(dllexport) int live_pool_destroy(void* value) {
    if(!value)return 1;
    auto* pool=static_cast<OwnedTexturePool*>(value);
    // Check before taking ownership: wrong-thread calls must not destroy CUDA state.
    try {pool->texture->check();}
    catch(const std::exception& e){projection_texture_error=e.what();return 0;}
    std::unique_ptr<OwnedTexturePool> owner(pool);
    try {pool->texture->close();return 1;}
    catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
