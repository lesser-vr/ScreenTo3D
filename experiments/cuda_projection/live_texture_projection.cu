// Diagnostic extension only. Borrows the exact pinned LiveDepth layout and stream.
// No application DLL or Python runtime path is replaced by this experiment.
#include "live_depth.cu"
#define DEPTHSBS_TEXTURE_LIBRARY
#include "texture_handoff_probe.cu"
#include <thread>

__global__ void pack_eye_surface(const unsigned char* rgb,cudaSurfaceObject_t surface,
    int width,int height,int eye) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=width*height)return;
    uchar4 pixel=make_uchar4(rgb[i*3],rgb[i*3+1],rgb[i*3+2],255);
    surf2Dwrite(pixel,surface,(i%width+eye*width)*4,i/width);
}
struct ProjectionTexture {
    ComPtr<ID3D11Device> producer;
    ComPtr<ID3D11Device1> reader;
    ComPtr<ID3D11DeviceContext> context;
    Slot slots[2];
    int w,h,next=0;
    std::thread::id owner=std::this_thread::get_id();
    ProjectionTexture(int width,int height,bool diagnostic=true):w(width),h(height) {
        if(w<16 || h<16 || w>4096 || h>2160)throw std::runtime_error("Invalid dimensions");
        int device=0;CU(cudaGetDevice(&device));cudaDeviceProp prop={};CU(cudaGetDeviceProperties(&prop,device));
        ComPtr<IDXGIFactory1> factory;hr(CreateDXGIFactory1(IID_PPV_ARGS(&factory)),"DXGI factory");
        ComPtr<IDXGIAdapter1> adapter;
        for(UINT i=0;;i++) {
            ComPtr<IDXGIAdapter1> candidate;auto result=factory->EnumAdapters1(i,&candidate);
            if(result==DXGI_ERROR_NOT_FOUND)break;hr(result,"Enumerate adapter");
            DXGI_ADAPTER_DESC1 desc={};hr(candidate->GetDesc1(&desc),"Adapter desc");
            if(!memcmp(&desc.AdapterLuid,prop.luid,sizeof(LUID))){adapter=candidate;break;}
        }
        if(!adapter)throw std::runtime_error("CUDA adapter mismatch");
        ComPtr<ID3D11Device> consumer;
        hr(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,
            D3D11_SDK_VERSION,&producer,nullptr,nullptr),"Producer device");
        hr(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,
            D3D11_SDK_VERSION,&consumer,nullptr,&context),"Consumer device");
        hr(consumer.As(&reader),"Consumer device1");
        for(auto& slot:slots)slot.create(producer.Get(),reader.Get(),w*2,h,diagnostic);
    }
    void check(){if(owner!=std::this_thread::get_id())throw std::runtime_error("Wrong texture owner");}
    void project(LiveDepth* c,float convergence,float scale,int coverage,unsigned char* diagnostic) {
        check();if(!c || c->w!=w || c->h!=h || !diagnostic || !std::isfinite(convergence) || !std::isfinite(scale) ||
            scale<0 || (coverage!=0 && coverage!=1))throw std::runtime_error("Invalid borrowed projection descriptor");
        auto& slot=slots[next];auto stream=c->stream;int blocks=(c->n+255)/256;
        cudaExternalSemaphoreWaitParams wait={};wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        make_shift<<<blocks,256,0,stream>>>(*c,convergence,scale);
        for(int eye=0;eye<2;eye++) {
            if(eye)negate_shift<<<blocks,256,0,stream>>>(c->shift,c->n);
            CU(cudaMemsetAsync(c->owners,0,c->n*8,stream));
            splat<<<blocks,256,0,stream>>>(c->aligned,c->shift,c->owners,w,c->n,coverage!=0);
            if(c->parallel_resolve)launch_resolve_parallel(c->rgb,c->owners,c->output,w,h,stream);
            else resolve<<<(h+63)/64,64,0,stream>>>(c->rgb,c->owners,c->output,w,h);
            pack_eye_surface<<<blocks,256,0,stream>>>(c->output,slot.surface,w,h,eye);
            CU(cudaGetLastError());
        }
        cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));CU(cudaStreamSynchronize(stream));
        hr(slot.reader_mutex->AcquireSync(1,2000),"Diagnostic acquire");slot.reader_locked=true;
        // Only the oracle reads pixels back; projection itself writes the surface.
        context->CopyResource(slot.staging.Get(),slot.reader.Get());D3D11_MAPPED_SUBRESOURCE mapped={};
        hr(context->Map(slot.staging.Get(),0,D3D11_MAP_READ,0,&mapped),"Diagnostic map");
        for(int y=0;y<h;y++)memcpy(diagnostic+static_cast<size_t>(y)*w*8,
            static_cast<unsigned char*>(mapped.pData)+static_cast<size_t>(y)*mapped.RowPitch,w*8);
        context->Unmap(slot.staging.Get(),0);
        hr(slot.reader_mutex->ReleaseSync(0),"Diagnostic release");slot.reader_locked=false;next=1-next;
    }
    void close(){check();for(auto& slot:slots)slot.close();}
};
static thread_local std::string projection_texture_error;
extern "C" __declspec(dllexport) const char* live_texture_error(){return projection_texture_error.c_str();}
extern "C" __declspec(dllexport) void* live_texture_create(int w,int h) {
    try{return new ProjectionTexture(w,h);}catch(const std::exception& e){projection_texture_error=e.what();return nullptr;}
}
extern "C" __declspec(dllexport) int live_texture_project(void* value,void* live,float convergence,float scale,int coverage,unsigned char* output) {
    try{static_cast<ProjectionTexture*>(value)->project(static_cast<LiveDepth*>(live),convergence,scale,coverage,output);return 1;}
    catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int live_texture_destroy(void* value) {
    auto* texture=static_cast<ProjectionTexture*>(value);
    try{texture->close();delete texture;return 1;}
    catch(const std::exception& e){projection_texture_error=e.what();delete texture;return 0;}
}
