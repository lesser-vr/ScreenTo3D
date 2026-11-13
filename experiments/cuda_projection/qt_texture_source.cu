// Standalone Qt boundary source, deliberately not part of the live application.
#define SCREENTO3D_TEXTURE_LIBRARY
#include "texture_handoff_probe.cu"
#include <thread>
#include <atomic>

struct TextureSource {
    ComPtr<ID3D11Device> producer;
    ComPtr<ID3D11Device1> reader;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11Query> completion;
    Slot slots[2];
    cudaStream_t stream=nullptr;
    int width,height,active=-1;
    std::thread::id owner=std::this_thread::get_id();
    TextureSource(ID3D11Device* device,int w,int h):width(w),height(h) {
        if(!device || w<1 || h<1 || w>8192 || h>4320)throw std::runtime_error("Invalid texture descriptor");
        ComPtr<IDXGIDevice> dxgi;hr(device->QueryInterface(IID_PPV_ARGS(&dxgi)),"Qt DXGI device");
        ComPtr<IDXGIAdapter> adapter;hr(dxgi->GetAdapter(&adapter),"Qt adapter");
        DXGI_ADAPTER_DESC desc={};hr(adapter->GetDesc(&desc),"Qt adapter desc");
        int cudaDevice=0;CU(cudaGetDevice(&cudaDevice));cudaDeviceProp prop={};
        CU(cudaGetDeviceProperties(&prop,cudaDevice));
        if(memcmp(&desc.AdapterLuid,prop.luid,sizeof(LUID)))throw std::runtime_error("Qt/CUDA adapter mismatch");
        hr(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,
            D3D11_SDK_VERSION,&producer,nullptr,nullptr),"CUDA producer device");
        hr(device->QueryInterface(IID_PPV_ARGS(&reader)),"Qt device1");
        device->GetImmediateContext(&context);
        D3D11_QUERY_DESC query={D3D11_QUERY_EVENT,0};
        hr(device->CreateQuery(&query,&completion),"Qt completion query");
        for(auto& slot:slots)slot.create(producer.Get(),reader.Get(),w,h,false);
        CU(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
    }
    void check() {if(owner!=std::this_thread::get_id())throw std::runtime_error("Wrong texture owner thread");}
    void begin(int index,int frame,bool clear) {
        check();
        // grabWindow can render without an afterFrameEnd callback. Retain its
        // lease until the next render, then prove completion before writing.
        if(active!=-1)end();
        if(index<0 || index>1)throw std::runtime_error("Invalid texture lease");
        auto& slot=slots[index];
        cudaExternalSemaphoreWaitParams wait={};wait.params.keyedMutex.key=0;
        wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        paint<<<dim3((width+31)/32,(height+7)/8),dim3(32,8),0,stream>>>(slot.surface,width,height,frame,clear);
        CU(cudaGetLastError());
        cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));
        CU(cudaStreamSynchronize(stream));
        hr(slot.reader_mutex->AcquireSync(1,2000),"Qt acquire texture");
        slot.reader_locked=true;active=index;
    }
    void end() {
        check();if(active==-1)return;
        // Qt afterFrameEnd has submitted its commands. Prove GPU completion before
        // making this slot writable again. Bounded diagnostic, not fast-path claim.
        context->End(completion.Get());context->Flush();
        auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
        BOOL done=FALSE;
        while(true) {
            HRESULT result=context->GetData(completion.Get(),&done,sizeof(done),0);
            if(result==S_OK && done)break;
            if(result!=S_FALSE && result!=S_OK)hr(result,"Qt GPU completion");
            if(std::chrono::steady_clock::now()>deadline)throw std::runtime_error("Qt GPU completion timeout");
            std::this_thread::yield();
        }
        hr(slots[active].reader_mutex->ReleaseSync(0),"Qt release texture");
        slots[active].reader_locked=false;active=-1;
    }
    ~TextureSource() {
        if(stream)cudaStreamSynchronize(stream);
        // The owner must call end before destruction; errors are surfaced by API.
        if(stream)cudaStreamDestroy(stream);
    }
};

static thread_local std::string texture_error;
static std::atomic<int> live_sources{0},created_sources{0},closed_sources{0};
#define EXPORT extern "C" __declspec(dllexport)
EXPORT void texture_counts(int* live,int* created,int* closed) {
    *live=live_sources.load();*created=created_sources.load();*closed=closed_sources.load();
}
EXPORT const char* texture_last_error(){return texture_error.c_str();}
EXPORT void* texture_create(void* device,int w,int h) {
    try {auto* source=new TextureSource(static_cast<ID3D11Device*>(device),w,h);live_sources++;created_sources++;return source;}
    catch(const std::exception& e){texture_error=e.what();return nullptr;}
}
EXPORT void* texture_handle(void* value,int index) {
    auto* source=static_cast<TextureSource*>(value);
    if(!source || index<0 || index>1)return nullptr;
    return source->slots[index].reader.Get();
}
EXPORT int texture_begin(void* value,int index,int frame,int clear) {
    try {static_cast<TextureSource*>(value)->begin(index,frame,clear!=0);return 1;}
    catch(const std::exception& e){texture_error=e.what();return 0;}
}
EXPORT int texture_end(void* value) {
    try {static_cast<TextureSource*>(value)->end();return 1;}
    catch(const std::exception& e){texture_error=e.what();return 0;}
}
EXPORT int texture_destroy(void* value) {
    try {
        auto* source=static_cast<TextureSource*>(value);source->check();source->end();
        for(auto& slot:source->slots)slot.close();delete source;live_sources--;closed_sources++;return 1;
    } catch(const std::exception& e){texture_error=e.what();return 0;}
}
