// Owned WGC -> D3D11 -> CUDA input. No captured pixels enter host memory.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <roapi.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include <cuda_runtime.h>
#include <cuda_d3d11_interop.h>
#include <atomic>
#include <memory>
#include <mutex>
#include <exception>

using namespace winrt;
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;
using winrt::Windows::Graphics::SizeInt32;
using ::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess;

static int64_t now_ns() {
    LARGE_INTEGER n,f;QueryPerformanceCounter(&n);QueryPerformanceFrequency(&f);
    return int64_t((long double)n.QuadPart*1000000000.L/f.QuadPart);
}
static void cuda_check(cudaError_t code) { if(code!=cudaSuccess)throw hresult_error(E_FAIL,to_hstring(cudaGetErrorString(code))); }

struct CaptureState {
    std::mutex mutex;
    std::atomic<bool> stopping{false},closed{false};
    com_ptr<ID3D11Device> device;
    com_ptr<ID3D11DeviceContext> context;
    IDirect3DDevice wrapped{nullptr};
    GraphicsCaptureItem item{nullptr};
    Direct3D11CaptureFramePool pool{nullptr};
    GraphicsCaptureSession session{nullptr};
    Direct3D11CaptureFrame latest{nullptr};
    event_token arrival{},closure{};
    bool arrivalRegistered=false,closureRegistered=false;
    SizeInt32 poolSize{};
    uint64_t sequence=0,replaced=0;
    int64_t callback=0;
};
struct Capture {
    std::shared_ptr<CaptureState> state=std::make_shared<CaptureState>();
    Direct3D11CaptureFrame held{nullptr};
    com_ptr<ID3D11Texture2D> bridge;
    cudaGraphicsResource* resource=nullptr;
    DWORD owner=GetCurrentThreadId();
    int device=0,width=0,height=0;
    bool apartment=false;
    void check() {int current=-1;cuda_check(cudaGetDevice(&current));if(owner!=GetCurrentThreadId()||current!=device)throw hresult_error(E_UNEXPECTED);}
    void release_bridge() { if(resource){cuda_check(cudaGraphicsUnregisterResource(resource));resource=nullptr;}bridge=nullptr; }
    void close() {
        if(!state)return;
        std::exception_ptr failure;
        auto attempt=[&](auto action){try{action();}catch(...){if(!failure)failure=std::current_exception();}};
        state->stopping=true;
        if(state->arrivalRegistered)attempt([&]{state->pool.FrameArrived(state->arrival);state->arrivalRegistered=false;});
        if(state->closureRegistered)attempt([&]{state->item.Closed(state->closure);state->closureRegistered=false;});
        if(state->session)attempt([&]{state->session.Close();state->session=nullptr;});
        attempt([&]{std::lock_guard<std::mutex> guard(state->mutex);if(state->latest)state->latest.Close();state->latest=nullptr;});
        attempt([&]{if(held)held.Close();held=nullptr;});
        if(state->pool)attempt([&]{state->pool.Close();state->pool=nullptr;});
        attempt([&]{release_bridge();});
        if(failure)std::rethrow_exception(failure);
        state.reset();
        if(apartment){RoUninitialize();apartment=false;}
    }
};

extern "C" __declspec(dllexport) int gpu_capture_create(void** out,uint64_t target,int monitor,int cursor,int device) {
    if(!out||!target||(monitor!=0&&monitor!=1)||(cursor!=0&&cursor!=1))return E_INVALIDARG;
    *out=nullptr;
    auto c=std::make_unique<Capture>();
    try {
        c->device=device;c->check();
        HRESULT hr=RoInitialize(RO_INIT_MULTITHREADED);
        if(SUCCEEDED(hr))c->apartment=true;else if(hr!=RPC_E_CHANGED_MODE)check_hresult(hr);
        if(!GraphicsCaptureSession::IsSupported())throw hresult_error(E_NOTIMPL);
        com_ptr<IDXGIFactory1> factory;check_hresult(CreateDXGIFactory1(__uuidof(IDXGIFactory1),factory.put_void()));
        com_ptr<IDXGIAdapter1> selected;
        for(unsigned i=0;;++i){com_ptr<IDXGIAdapter1> a;auto result=factory->EnumAdapters1(i,a.put());
            if(result==DXGI_ERROR_NOT_FOUND)break;check_hresult(result);
            int id=-1;if(cudaD3D11GetDevice(&id,a.get())==cudaSuccess&&id==device){selected=a;break;}cudaGetLastError();}
        if(!selected)throw hresult_error(E_NOINTERFACE);
        auto& s=*c->state;
        check_hresult(D3D11CreateDevice(selected.get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            nullptr,0,D3D11_SDK_VERSION,s.device.put(),nullptr,s.context.put()));
        auto dxgi=s.device.as<IDXGIDevice>();com_ptr<IInspectable> inspectable;
        check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgi.get(),inspectable.put()));s.wrapped=inspectable.as<IDirect3DDevice>();
        auto interop=get_activation_factory<GraphicsCaptureItem,IGraphicsCaptureItemInterop>();
        if(monitor)check_hresult(interop->CreateForMonitor((HMONITOR)target,guid_of<GraphicsCaptureItem>(),put_abi(s.item)));
        else check_hresult(interop->CreateForWindow((HWND)target,guid_of<GraphicsCaptureItem>(),put_abi(s.item)));
        s.poolSize=s.item.Size();
        if(s.poolSize.Width<16||s.poolSize.Width>4096||s.poolSize.Height<16||s.poolSize.Height>2160)throw hresult_error(E_INVALIDARG);
        // Fixed bounded capacity avoids old-size surfaces and lost static frames
        // during Recreate. Only ContentSize pixels are copied to CUDA. Two BGRA
        // buffers reserve at most 67.5 MiB; no full-capacity host readback exists.
        s.poolSize={4096,2160};
        s.pool=Direct3D11CaptureFramePool::CreateFreeThreaded(s.wrapped,DirectXPixelFormat::B8G8R8A8UIntNormalized,2,s.poolSize);
        std::weak_ptr<CaptureState> weak=c->state;
        s.arrival=s.pool.FrameArrived([weak](auto const& sender,auto const&){
            auto state=weak.lock();if(!state||state->stopping)return;
            try {auto frame=sender.TryGetNextFrame();if(!frame)return;auto callback=now_ns();
                std::lock_guard<std::mutex> guard(state->mutex);
                if(state->stopping){frame.Close();return;}
                if(state->latest){state->latest.Close();++state->replaced;}
                state->latest=frame;state->callback=callback;++state->sequence;
            }catch(...){if(!state->stopping)state->closed=true;}
        });
        s.arrivalRegistered=true;
        s.closure=s.item.Closed([weak](auto const&,auto const&){if(auto s=weak.lock())s->closed=true;});
        s.closureRegistered=true;
        s.session=s.pool.CreateCaptureSession(s.item);s.session.IsCursorCaptureEnabled(cursor!=0);
        // Keep the OS capture border; no permission to hide it or alter affinity.
        if(auto rate=s.session.try_as<IGraphicsCaptureSession5>())rate.MinUpdateInterval(winrt::Windows::Foundation::TimeSpan{0});
        s.session.StartCapture();*out=c.release();return 0;
    }catch(hresult_error const& e){int code=e.code();try{c->close();}catch(...){}return code;}
    catch(...){try{c->close();}catch(...){}return E_FAIL;}
}

// 0=no new frame, 1=owned frame, negative=HRESULT. info: w,h,seq,source,callback,replaced.
extern "C" __declspec(dllexport) int gpu_capture_acquire(void* handle,int64_t* info) {
    if(!handle||!info)return E_INVALIDARG;auto c=(Capture*)handle;
    try {
        c->check();if(c->held)throw hresult_error(E_UNEXPECTED);
        auto& s=*c->state;if(s.closed)throw hresult_error(RO_E_CLOSED);
        {std::lock_guard<std::mutex> guard(s.mutex);if(!s.latest)return 0;c->held=std::move(s.latest);s.latest=nullptr;
            info[2]=s.sequence;info[4]=s.callback;info[5]=s.replaced;}
        auto size=c->held.ContentSize();info[0]=size.Width;info[1]=size.Height;info[3]=c->held.SystemRelativeTime().count()*100;
        if(size.Width<16||size.Width>4096||size.Height<16||size.Height>2160)throw hresult_error(E_INVALIDARG);
        c->width=size.Width;c->height=size.Height;return 1;
    }catch(hresult_error const& e){return e.code();}catch(...){return E_FAIL;}
}

extern "C" __declspec(dllexport) int gpu_capture_copy(void* handle,void* dst,size_t bytes,void* stream) {
    if(!handle||!dst||!stream)return E_INVALIDARG;auto c=(Capture*)handle;
    bool mapped=false;
    try {
        c->check();if(!c->held||bytes!=size_t(c->width)*c->height*4)throw hresult_error(E_INVALIDARG);
        auto access=c->held.Surface().as<IDirect3DDxgiInterfaceAccess>();com_ptr<ID3D11Texture2D> src;
        check_hresult(access->GetInterface(__uuidof(ID3D11Texture2D),src.put_void()));
        D3D11_TEXTURE2D_DESC desc{};src->GetDesc(&desc);
        if(desc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM||desc.Width<unsigned(c->width)||desc.Height<unsigned(c->height))throw hresult_error(E_INVALIDARG);
        D3D11_TEXTURE2D_DESC current{};if(c->bridge)c->bridge->GetDesc(&current);
        if(!c->bridge||current.Width!=unsigned(c->width)||current.Height!=unsigned(c->height)){
            c->release_bridge();desc.Width=c->width;desc.Height=c->height;desc.Usage=D3D11_USAGE_DEFAULT;
            desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;desc.CPUAccessFlags=0;desc.MiscFlags=0;
            check_hresult(c->state->device->CreateTexture2D(&desc,nullptr,c->bridge.put()));
            cuda_check(cudaGraphicsD3D11RegisterResource(&c->resource,c->bridge.get(),cudaGraphicsRegisterFlagsNone));
        }
        D3D11_BOX box{0,0,0,unsigned(c->width),unsigned(c->height),1};
        c->state->context->CopySubresourceRegion(c->bridge.get(),0,0,0,0,src.get(),0,&box);c->state->context->Flush();
        auto cuStream=(cudaStream_t)stream;cuda_check(cudaGraphicsMapResources(1,&c->resource,cuStream));mapped=true;
        cudaArray_t array;cuda_check(cudaGraphicsSubResourceGetMappedArray(&array,c->resource,0,0));
        cuda_check(cudaMemcpy2DFromArrayAsync(dst,c->width*4,array,0,0,c->width*4,c->height,cudaMemcpyDeviceToDevice,cuStream));
        cuda_check(cudaGraphicsUnmapResources(1,&c->resource,cuStream));mapped=false;
        cuda_check(cudaStreamSynchronize(cuStream));c->held.Close();c->held=nullptr;return 0;
    }catch(hresult_error const& e){if(mapped)cudaGraphicsUnmapResources(1,&c->resource,(cudaStream_t)stream);cudaStreamSynchronize((cudaStream_t)stream);return e.code();}
    catch(...){return E_FAIL;}
}

extern "C" __declspec(dllexport) int gpu_capture_destroy(void* handle) {
    if(!handle)return 0;auto c=(Capture*)handle;
    try{c->check();c->close();delete c;return 0;}catch(hresult_error const& e){return e.code();}catch(...){return E_FAIL;}
}
