// Standalone CUDA/D3D11 boundary probe. No capture, Qt or model integration.
#define NOMINMAX
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <cuda_runtime.h>
#include <cuda_d3d11_interop.h>
#include <chrono>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>

using Microsoft::WRL::ComPtr;
static void hr(HRESULT code,const char* label) {
    // WAIT_TIMEOUT is not a failed HRESULT. Treat it as failure too.
    if(code!=S_OK)throw std::runtime_error(std::string(label)+": "+std::to_string(code));
}
static void cu(cudaError_t code,const char* label) {
    if(code!=cudaSuccess)throw std::runtime_error(std::string(label)+": "+cudaGetErrorString(code));
}
#define CU(call) cu((call),#call)

__global__ void paint(cudaSurfaceObject_t surface,int w,int h,int frame,bool clear) {
    int x=blockIdx.x*blockDim.x+threadIdx.x;
    int y=blockIdx.y*blockDim.y+threadIdx.y;
    if(x>=w || y>=h)return;
    uchar4 pixel=clear?make_uchar4(0,0,0,255):make_uchar4(
        (x+frame)%256,(y+frame*3)%256,(x+y+frame*7)%256,255);
    surf2Dwrite(pixel,surface,x*4,y);
}

struct Slot {
    ComPtr<ID3D11Texture2D> writer,reader,staging;
    ComPtr<IDXGIKeyedMutex> writer_mutex,reader_mutex;
    cudaExternalMemory_t memory=nullptr;
    cudaExternalSemaphore_t semaphore=nullptr;
    cudaMipmappedArray_t mipmap=nullptr;
    HANDLE shared=nullptr;
    bool writer_locked=false,reader_locked=false;
    cudaSurfaceObject_t surface=0;
    ~Slot() {
        // Error-path cleanup must not destroy a surface while its kernel runs.
        if(surface)cudaDeviceSynchronize();
        if(surface)cudaDestroySurfaceObject(surface);
        if(mipmap)cudaFreeMipmappedArray(mipmap);
        if(semaphore)cudaDestroyExternalSemaphore(semaphore);
        if(memory)cudaDestroyExternalMemory(memory);
        if(writer_locked)writer_mutex->ReleaseSync(0);
        if(reader_locked)reader_mutex->ReleaseSync(0);
        if(shared)CloseHandle(shared);
    }
    void create(ID3D11Device* producer,ID3D11Device1* consumer,int w,int h,bool diagnostic=true) {
        D3D11_TEXTURE2D_DESC desc={};
        desc.Width=w;desc.Height=h;desc.MipLevels=1;desc.ArraySize=1;
        desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;
        desc.Usage=D3D11_USAGE_DEFAULT;
        desc.BindFlags=D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET;
        desc.MiscFlags=D3D11_RESOURCE_MISC_SHARED_NTHANDLE|D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX;
        hr(producer->CreateTexture2D(&desc,nullptr,&writer),"CreateTexture2D");
        ComPtr<IDXGIResource1> dxgi;
        hr(writer.As(&dxgi),"IDXGIResource1");
        hr(dxgi->CreateSharedHandle(nullptr,DXGI_SHARED_RESOURCE_READ|DXGI_SHARED_RESOURCE_WRITE,
            nullptr,&shared),"CreateSharedHandle");
        hr(consumer->OpenSharedResource1(shared,IID_PPV_ARGS(&reader)),"OpenSharedResource1");
        hr(writer.As(&writer_mutex),"writer keyed mutex");
        hr(reader.As(&reader_mutex),"reader keyed mutex");
        cudaExternalMemoryHandleDesc external={};
        external.type=cudaExternalMemoryHandleTypeD3D11Resource;
        external.handle.win32.handle=shared;
        external.size=static_cast<unsigned long long>(w)*h*4;
        external.flags=cudaExternalMemoryDedicated;
        CU(cudaImportExternalMemory(&memory,&external));
        cudaExternalMemoryMipmappedArrayDesc mapping={};
        mapping.formatDesc=cudaCreateChannelDesc<uchar4>();
        mapping.extent=make_cudaExtent(w,h,0);
        mapping.flags=cudaArraySurfaceLoadStore|cudaArrayColorAttachment;
        mapping.numLevels=1;
        CU(cudaExternalMemoryGetMappedMipmappedArray(&mipmap,memory,&mapping));
        cudaArray_t array=nullptr;
        CU(cudaGetMipmappedArrayLevel(&array,mipmap,0));
        cudaResourceDesc resource={};resource.resType=cudaResourceTypeArray;
        resource.res.array.array=array;
        CU(cudaCreateSurfaceObject(&surface,&resource));
        cudaExternalSemaphoreHandleDesc sync={};
        sync.type=cudaExternalSemaphoreHandleTypeKeyedMutex;
        sync.handle.win32.handle=shared;
        CU(cudaImportExternalSemaphore(&semaphore,&sync));
        hr(writer_mutex->AcquireSync(0,2000),"initialize AcquireSync");
        writer_locked=true;
        hr(writer_mutex->ReleaseSync(0),"initialize ReleaseSync");
        writer_locked=false;
        CloseHandle(shared);shared=nullptr;
        if(diagnostic) {
            desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.MiscFlags=0;
            desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
            hr(consumer->CreateTexture2D(&desc,nullptr,&staging),"Create diagnostic staging");
        }
    }
    void close() {
        if(writer_locked || reader_locked)
            throw std::runtime_error("Slot still borrowed at close");
        if(surface){CU(cudaDestroySurfaceObject(surface));surface=0;}
        if(mipmap){CU(cudaFreeMipmappedArray(mipmap));mipmap=nullptr;}
        if(semaphore){CU(cudaDestroyExternalSemaphore(semaphore));semaphore=nullptr;}
        if(memory){CU(cudaDestroyExternalMemory(memory));memory=nullptr;}
        staging.Reset();reader_mutex.Reset();writer_mutex.Reset();reader.Reset();writer.Reset();
    }
};

#ifndef DEPTHSBS_TEXTURE_LIBRARY
static void run_case(ID3D11Device* writer,ID3D11Device1* reader,
    ID3D11DeviceContext* consumer,cudaStream_t stream,int w,int h,int cycle) {
    Slot slots[2];
    for(auto& slot:slots)slot.create(writer,reader,w,h);
    std::vector<double> handoff_ms;
    int verified=0;
    for(int frame=0;frame<32;frame++) {
        auto& slot=slots[frame%2];
        bool clear=frame>=30;
        auto began=std::chrono::steady_clock::now();
        cudaExternalSemaphoreWaitParams wait={};
        wait.params.keyedMutex.key=0;
        wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        paint<<<dim3((w+31)/32,(h+7)/8),dim3(32,8),0,stream>>>(slot.surface,w,h,frame,clear);
        CU(cudaGetLastError());
        cudaExternalSemaphoreSignalParams signal={};
        signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));
        CU(cudaStreamSynchronize(stream));
        hr(slot.reader_mutex->AcquireSync(1,2000),"reader AcquireSync");slot.reader_locked=true;
        auto ended=std::chrono::steady_clock::now();
        if(frame>=3 && !clear)
            handoff_ms.push_back(std::chrono::duration<double,std::milli>(ended-began).count());
        // Diagnostic readback is deliberately outside handoff timing.
        consumer->CopyResource(slot.staging.Get(),slot.reader.Get());
        D3D11_MAPPED_SUBRESOURCE mapped={};
        hr(consumer->Map(slot.staging.Get(),0,D3D11_MAP_READ,0,&mapped),"diagnostic Map");
        bool exact=true;
        for(int y=0;y<h && exact;y++)for(int x=0;x<w;x++) {
            auto p=static_cast<unsigned char*>(mapped.pData)+y*mapped.RowPitch+x*4;
            unsigned char r=clear?0:(x+frame)%256,g=clear?0:(y+frame*3)%256,
                b=clear?0:(x+y+frame*7)%256;
            if(p[0]!=r || p[1]!=g || p[2]!=b || p[3]!=255){exact=false;break;}
        }
        consumer->Unmap(slot.staging.Get(),0);
        hr(slot.reader_mutex->ReleaseSync(0),"reader ReleaseSync");slot.reader_locked=false;
        if(!exact)throw std::runtime_error("Shared texture pixel mismatch");
        verified++;
    }
    for(auto& slot:slots)slot.close();
    auto sorted=handoff_ms;std::sort(sorted.begin(),sorted.end());
    std::printf("{\"cycle\":%d,\"width\":%d,\"height\":%d,\"slots\":2,\"exact_frames\":%d,"
        "\"clear_frames\":2,\"handoff_median_ms\":%.6f,\"handoff_ms\":[",cycle,w,h,verified,sorted[sorted.size()/2]);
    for(size_t i=0;i<handoff_ms.size();i++)std::printf("%s%.6f",i?",":"",handoff_ms[i]);
    std::printf("]}\n");std::fflush(stdout);
}

int main() {
    cudaStream_t stream=nullptr;
    try {
        int device=0;CU(cudaGetDevice(&device));cudaDeviceProp prop={};
        CU(cudaGetDeviceProperties(&prop,device));
        ComPtr<IDXGIFactory1> factory;hr(CreateDXGIFactory1(IID_PPV_ARGS(&factory)),"DXGI factory");
        ComPtr<IDXGIAdapter1> adapter;
        for(UINT i=0;;i++) {
            ComPtr<IDXGIAdapter1> current;
            if(factory->EnumAdapters1(i,&current)==DXGI_ERROR_NOT_FOUND)break;
            DXGI_ADAPTER_DESC1 desc={};hr(current->GetDesc1(&desc),"adapter description");
            if(!memcmp(&desc.AdapterLuid,prop.luid,sizeof(LUID))){adapter=current;break;}
        }
        if(!adapter)throw std::runtime_error("No D3D adapter matching CUDA LUID");
        ComPtr<ID3D11Device> producer,consumer_device;
        ComPtr<ID3D11DeviceContext> producer_context,consumer_context;
        const D3D_FEATURE_LEVEL requested[]={D3D_FEATURE_LEVEL_11_0};
        hr(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,requested,1,
            D3D11_SDK_VERSION,&producer,nullptr,&producer_context),"producer device");
        hr(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,requested,1,
            D3D11_SDK_VERSION,&consumer_device,nullptr,&consumer_context),"consumer device");
        ComPtr<ID3D11Device1> consumer;hr(consumer_device.As(&consumer),"consumer device1");
        CU(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
        std::printf("{\"gpu\":\"%s\",\"scope\":\"two D3D devices in one process, synthetic CUDA pixels; no Qt, capture, cross-process or display fps claim\"}\n",prop.name);
        for(int cycle=0;cycle<2;cycle++) {
            run_case(producer.Get(),consumer.Get(),consumer_context.Get(),stream,3840,1080,cycle);
            run_case(producer.Get(),consumer.Get(),consumer_context.Get(),stream,1200,420,cycle);
            run_case(producer.Get(),consumer.Get(),consumer_context.Get(),stream,7680,2160,cycle);
        }
        CU(cudaStreamDestroy(stream));stream=nullptr;
        std::puts("{\"passed\":true,\"exact_frames\":192,\"explicit_resource_cleanup\":true}");
        return 0;
    } catch(const std::exception& error) {
        if(stream){cudaStreamSynchronize(stream);cudaStreamDestroy(stream);}
        std::fprintf(stderr,"Texture probe failed: %s\n",error.what());return 1;
    }
}
#endif
