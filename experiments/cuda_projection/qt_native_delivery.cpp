// Pure D3D11/Qt GUI consumer. Never link CUDA or TensorRT into this module.
#define NOMINMAX
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <QtQuick/QQuickItem>
#include <QtQuick/QQuickWindow>
#include <QtQuick/QSGSimpleTextureNode>
#include <QtQuick/QSGRendererInterface>
#include <QtQuick/qsgtexture_platform.h>
#include <QtQml/qqml.h>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

using Microsoft::WRL::ComPtr;
using Clock=std::chrono::steady_clock;
using Id=unsigned long long;
static void check(HRESULT code,const char* where) {
    if(code!=S_OK)throw std::runtime_error(std::string(where)+": "+std::to_string(code));
}
struct Handle {
    HANDLE value=nullptr;
    ~Handle(){if(value)CloseHandle(value);}
};
static std::mutex errorMutex;
static std::string failure;
static void fail(const std::string& value) noexcept {
    std::lock_guard<std::mutex> guard(errorMutex);if(failure.empty())failure=value;
}
static std::atomic<Id> activeSession{0};
static std::atomic<int> poolCount{0},nodeCount[2]{};
static std::mutex metricsMutex;
struct Metrics {
    std::atomic<Id> uploads{0},lastUpload{0},submits{0},lastSubmit{0},copyNs{0};
    void reset(){uploads=lastUpload=submits=lastSubmit=copyNs=0;}
};
static Metrics metrics[2];
// Protected by metricsMutex. Only distinct output submissions enter the ring.
static constexpr unsigned sampleCapacity = 4096;
struct OutputSample { Id endNs, sequence; };
static OutputSample outputSamples[sampleCapacity]{};
static Id outputSampleCount = 0;

struct Pool {
    Id session,generation;
    int width,height;
    LUID luid;
    Handle handles[2];
    ComPtr<ID3D11Device1> device;
    ComPtr<ID3D11Texture2D> sources[2];
    ComPtr<IDXGIKeyedMutex> mutexes[2];
    std::atomic<Id> released[2]{};
    Id published[2]={};
    std::atomic<bool> poisoned{false};
    bool counted=false;
    Pool(Id s,Id g,DWORD pid,Id h0,Id h1,int w,int h,DWORD low,LONG high):
        session(s),generation(g),width(w),height(h),luid{low,high} {
        if(!s || !g || !pid || !h0 || !h1 || h0==h1 || w<16 || w>8192 ||
            h<16 || h>4320 || static_cast<Id>(w)*h>8192ULL*2160)throw std::runtime_error("Invalid native pool descriptor");
        if(poolCount.load()>=3)throw std::runtime_error("Native pool lifetime bound exceeded");
        ComPtr<IDXGIFactory1> factory;
        check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)),"DXGI factory");
        ComPtr<IDXGIAdapter1> adapter;
        for(UINT i=0;;i++) {
            ComPtr<IDXGIAdapter1> candidate;auto result=factory->EnumAdapters1(i,&candidate);
            if(result==DXGI_ERROR_NOT_FOUND)break;check(result,"Adapter enumeration");
            DXGI_ADAPTER_DESC1 desc={};check(candidate->GetDesc1(&desc),"Adapter description");
            if(!memcmp(&desc.AdapterLuid,&luid,sizeof(luid))){adapter=candidate;break;}
        }
        if(!adapter)throw std::runtime_error("Native pool adapter is unavailable");
        ComPtr<ID3D11Device> base;
        check(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,
            D3D11_SDK_VERSION,&base,nullptr,nullptr),"Broker device");
        check(base.As(&device),"Broker device1");
        Handle process;process.value=OpenProcess(PROCESS_DUP_HANDLE,FALSE,pid);
        if(!process.value)throw std::runtime_error("Cannot open owned texture worker");
        Id original[2]={h0,h1};
        for(int i=0;i<2;i++) {
            if(!DuplicateHandle(process.value,reinterpret_cast<HANDLE>(original[i]),
                GetCurrentProcess(),&handles[i].value,0,FALSE,DUPLICATE_SAME_ACCESS))
                throw std::runtime_error("Cannot duplicate owned texture handle");
            open(device.Get(),i,&sources[i]);
            check(sources[i].As(&mutexes[i]),"Broker keyed mutex");
        }
        poolCount++;counted=true;
    }
    void open(ID3D11Device1* target,int index,ID3D11Texture2D** output) {
        check(target->OpenSharedResource1(handles[index].value,__uuidof(ID3D11Texture2D),
            reinterpret_cast<void**>(output)),"Open texture resource");
        D3D11_TEXTURE2D_DESC desc={};(*output)->GetDesc(&desc);
        if(desc.Width!=static_cast<UINT>(width) || desc.Height!=static_cast<UINT>(height) ||
            desc.Format!=DXGI_FORMAT_R8G8B8A8_UNORM || desc.MipLevels!=1 || desc.ArraySize!=1 ||
            desc.SampleDesc.Count!=1 || desc.SampleDesc.Quality!=0 ||
            desc.Usage!=D3D11_USAGE_DEFAULT || desc.CPUAccessFlags!=0 ||
            !(desc.MiscFlags&D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX))
            throw std::runtime_error("Opened texture properties mismatch");
    }
    ~Pool(){if(counted)poolCount--;}
};
struct Frame {
    std::shared_ptr<Pool> pool;
    int slot;
    Id sequence;
    Frame(std::shared_ptr<Pool> p,int i,Id id):pool(std::move(p)),slot(i),sequence(id){}
    ~Frame() {
        if(pool->poisoned)return;
        try {
            check(pool->mutexes[slot]->AcquireSync(1,2000),"Last lease acquire");
            check(pool->mutexes[slot]->ReleaseSync(0),"Last lease release");
            pool->released[slot]=sequence;
        }catch(const std::exception& e){pool->poisoned=true;fail(e.what());}
    }
};
static std::mutex brokerMutex;
static std::shared_ptr<Pool> currentPool;
static std::shared_ptr<Frame> latest;
static Id lastSequence=0;
static std::shared_ptr<Frame> snapshot(Id session) {
    std::lock_guard<std::mutex> guard(brokerMutex);
    return activeSession==session?latest:nullptr;
}

struct NativeNode:QSGSimpleTextureNode {
    QQuickWindow* window;
    int consumer;
    Id session,sequence=0;
    std::shared_ptr<Pool> pool;
    ComPtr<ID3D11Device1> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11Texture2D> texture,sources[2];
    ComPtr<ID3D11RenderTargetView> clearTarget;
    ComPtr<IDXGIKeyedMutex> mutexes[2];
    ComPtr<ID3D11Query> complete;
    QMetaObject::Connection rendering,submitted;
    bool counted=false,refresh=true;
    NativeNode(QQuickWindow* win,int id,const std::shared_ptr<Frame>& frame):
        window(win),consumer(id),session(frame->pool->session),pool(frame->pool) {
        if(id<0 || id>1 || nodeCount[id].load()!=0)
            throw std::runtime_error("Only one render node per native consumer is supported");
        auto* ri=window->rendererInterface();
        if(ri->graphicsApi()!=QSGRendererInterface::Direct3D11)
            throw std::runtime_error("Native delivery requires Qt D3D11");
        auto* base=static_cast<ID3D11Device*>(ri->getResource(window,QSGRendererInterface::DeviceResource));
        if(!base)throw std::runtime_error("Qt D3D11 device missing");
        check(base->QueryInterface(IID_PPV_ARGS(&device)),"Qt device1");
        ComPtr<IDXGIDevice> dxgi;check(device.As(&dxgi),"Qt DXGI device");
        ComPtr<IDXGIAdapter> adapter;check(dxgi->GetAdapter(&adapter),"Qt adapter");
        DXGI_ADAPTER_DESC desc={};check(adapter->GetDesc(&desc),"Qt adapter description");
        if(memcmp(&desc.AdapterLuid,&pool->luid,sizeof(LUID)))
            throw std::runtime_error("Qt and CUDA adapters differ");
        device->GetImmediateContext(&context);
        for(int i=0;i<2;i++) {
            pool->open(device.Get(),i,&sources[i]);
            check(sources[i].As(&mutexes[i]),"Consumer keyed mutex");
        }
        D3D11_TEXTURE2D_DESC td={};td.Width=pool->width;td.Height=pool->height;
        td.MipLevels=td.ArraySize=td.SampleDesc.Count=1;
        td.Format=DXGI_FORMAT_R8G8B8A8_UNORM;td.Usage=D3D11_USAGE_DEFAULT;
        td.BindFlags=D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET;
        check(device->CreateTexture2D(&td,nullptr,&texture),"Private Qt texture");
        check(device->CreateRenderTargetView(texture.Get(),nullptr,&clearTarget),"Private clear target");
        D3D11_QUERY_DESC query={D3D11_QUERY_EVENT,0};
        check(device->CreateQuery(&query,&complete),"GPU copy completion query");
        auto* wrapper=QNativeInterface::QSGD3D11Texture::fromNative(texture.Get(),window,
            QSize(pool->width,pool->height));
        if(!wrapper)throw std::runtime_error("Native texture wrapping failed");
        setTexture(wrapper);setOwnsTexture(true);setFiltering(QSGTexture::Linear);
        rendering=QObject::connect(window,&QQuickWindow::beforeRendering,window,[this] {
            window->beginExternalCommands();
            try {
                if(activeSession!=session)clear();
                else if(refresh) {
                    auto frame=snapshot(session);
                    if(frame && frame->pool==pool)copy(frame);
                    else clear();
                    refresh=false;
                }
            }catch(const std::exception& e){pool->poisoned=true;fail(e.what());clear();}
            window->endExternalCommands();
        },Qt::DirectConnection);
        submitted=QObject::connect(window,&QQuickWindow::afterFrameEnd,window,[this] {
            std::lock_guard<std::mutex> guard(metricsMutex);
            if(activeSession!=session || !sequence)return;
            auto& m=metrics[consumer];
            if(sequence!=m.lastSubmit.load()){
                m.lastSubmit=sequence;m.submits++;
                if(consumer==1){
                    // MSVC steady_clock and Python perf_counter_ns use Windows QPC.
                    auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        Clock::now().time_since_epoch()).count();
                    outputSamples[outputSampleCount++ % sampleCapacity] = {Id(ns), sequence};
                }
            }
        },Qt::DirectConnection);
        nodeCount[id]++;counted=true;
    }
    void copy(const std::shared_ptr<Frame>& frame) {
        if(sequence==frame->sequence)return;
        auto started=Clock::now();auto* mutex=mutexes[frame->slot].Get();
        check(mutex->AcquireSync(1,2000),"Consumer acquire");
        try {
            context->CopyResource(texture.Get(),sources[frame->slot].Get());
            context->End(complete.Get());context->Flush();
            for(;;) {
                BOOL done=FALSE;
                HRESULT result=context->GetData(complete.Get(),&done,sizeof(done),0);
                if(result==S_OK && done)break;
                if(result!=S_FALSE && result!=S_OK)check(result,"GPU copy completion");
                if(Clock::now()-started>std::chrono::seconds(2))
                    throw std::runtime_error("GPU copy completion timeout");
                SwitchToThread();
            }
        } catch(...) {
            // Returning the mutex after a failed copy is not proof of completed
            // GPU work. Fail the entire session; never reuse the slot normally.
            pool->poisoned=true;mutex->ReleaseSync(1);throw;
        }
        check(mutex->ReleaseSync(1),"Consumer release");
        sequence=frame->sequence;
        std::lock_guard<std::mutex> guard(metricsMutex);
        if(activeSession==session) {
            auto& m=metrics[consumer];m.uploads++;m.lastUpload=sequence;
            m.copyNs=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
        }
    }
    void clear() {
        const float black[4]={0,0,0,1};context->ClearRenderTargetView(clearTarget.Get(),black);
        sequence=0;
    }
    ~NativeNode() override {
        QObject::disconnect(rendering);
        QObject::disconnect(submitted);
        // QSG wrapper must die before its borrowed ID3D11Texture2D.
        auto* wrapper=QSGSimpleTextureNode::texture();setOwnsTexture(false);delete wrapper;
        if(counted)nodeCount[consumer]--;
    }
};

class NativeSurface:public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(qulonglong session READ session WRITE setSession NOTIFY changed)
    Q_PROPERTY(int consumer READ consumer WRITE setConsumer NOTIFY changed)
    Q_PROPERTY(bool enabledFrame READ enabledFrame WRITE setEnabledFrame NOTIFY changed)
    Q_PROPERTY(int revision READ revision WRITE setRevision NOTIFY changed)
    Id session_=0;int consumer_=0,revision_=0;bool enabled_=false;
public:
    NativeSurface(QQuickItem* parent=nullptr):QQuickItem(parent){setFlag(ItemHasContents,true);}
    Id session() const{return session_;} int consumer() const{return consumer_;}
    bool enabledFrame() const{return enabled_;} int revision() const{return revision_;}
    void setSession(Id value){if(session_!=value){session_=value;emit changed();update();}}
    void setConsumer(int value){if(consumer_!=value){consumer_=value;emit changed();update();}}
    void setEnabledFrame(bool value){if(enabled_!=value){enabled_=value;emit changed();update();}}
    void setRevision(int value){if(revision_!=value){revision_=value;emit changed();update();}}
signals:
    void changed();
protected:
    QSGNode* updatePaintNode(QSGNode* old,UpdatePaintNodeData*) override {
        auto* node=static_cast<NativeNode*>(old);
        try {
            auto frame=enabled_?snapshot(session_):nullptr;
            if(!frame){delete node;return nullptr;}
            if(node && (node->pool!=frame->pool || node->consumer!=consumer_)) {
                delete node;node=nullptr;
            }
            if(!node)node=new NativeNode(window(),consumer_,frame);
            node->refresh=true;
            QSizeF fitted(frame->pool->width,frame->pool->height);
            fitted.scale(boundingRect().size(),Qt::KeepAspectRatio);
            node->setRect(QRectF(QPointF((width()-fitted.width())/2,(height()-fitted.height())/2),fitted));
            node->markDirty(QSGNode::DirtyMaterial);
            // No frame lease survives sync. beforeRendering takes a fresh lease
            // inside Qt's external-command boundary, before its render pass.
            return node;
        }catch(const std::exception& e){fail(e.what());delete node;return nullptr;}
    }
};

extern "C" {
__declspec(dllexport) int native_register() {
    const int current=qmlRegisterType<NativeSurface>("ScreenTo3D.Native",1,0,"NativeSurface");
    const int interim=qmlRegisterType<NativeSurface>("StereoTo3D.Native",1,0,"NativeSurface");
    const int legacy=qmlRegisterType<NativeSurface>("DepthSBS.Native",1,0,"NativeSurface");
    return current>=0 && interim>=0 && legacy>=0;
}
__declspec(dllexport) const char* native_error() {
    static thread_local std::string result;std::lock_guard<std::mutex> guard(errorMutex);
    result=failure;return result.c_str();
}
__declspec(dllexport) int native_begin(Id session) {
    if(!session)return 0;
    std::shared_ptr<Frame> old;
    {std::lock_guard<std::mutex> guard(brokerMutex);activeSession=0;
     old=std::move(latest);currentPool.reset();lastSequence=0;}
    old.reset();
    {std::lock_guard<std::mutex> guard(errorMutex);failure.clear();}
    {std::lock_guard<std::mutex> guard(metricsMutex);
     for(auto& m:metrics)m.reset();outputSampleCount=0;activeSession=session;}return 1;
}
__declspec(dllexport) int native_install(Id session,Id generation,DWORD pid,Id h0,Id h1,
    int width,int height,DWORD low,LONG high) {
    try {
        std::lock_guard<std::mutex> guard(brokerMutex);
        if(activeSession!=session || currentPool || latest)
            throw std::runtime_error("Native pool installation state mismatch");
        currentPool=std::make_shared<Pool>(session,generation,pid,h0,h1,width,height,low,high);
        return 1;
    }catch(const std::exception& e){fail(e.what());return 0;}
}
__declspec(dllexport) int native_publish(Id session,Id generation,int slot,Id sequence) {
    std::shared_ptr<Frame> old;
    try {
        {std::lock_guard<std::mutex> guard(brokerMutex);
         if(activeSession!=session || !currentPool || currentPool->generation!=generation ||
            slot<0 || slot>1 || sequence<=lastSequence)
             throw std::runtime_error("Stale native frame descriptor");
         if(currentPool->poisoned || currentPool->published[slot]!=currentPool->released[slot].load())
             throw std::runtime_error("Native slot is poisoned or still leased");
         auto frame=std::make_shared<Frame>(currentPool,slot,sequence);
         currentPool->published[slot]=sequence;
         old=std::move(latest);latest=std::move(frame);lastSequence=sequence;}
        old.reset();return 1;
    }catch(const std::exception& e){fail(e.what());return 0;}
}
__declspec(dllexport) void native_retire() {
    std::shared_ptr<Frame> old;
    {std::lock_guard<std::mutex> guard(brokerMutex);old=std::move(latest);}
    old.reset();
}
__declspec(dllexport) int native_releases(Id* output) {
    if(!output)return 0;
    std::lock_guard<std::mutex> guard(brokerMutex);
    for(int i=0;i<2;i++)output[i]=currentPool?currentPool->released[i].load():0;
    return 1;
}
__declspec(dllexport) void native_drop_pool() {
    std::lock_guard<std::mutex> guard(brokerMutex);currentPool.reset();
}
__declspec(dllexport) void native_end() {
    activeSession=0;native_retire();native_drop_pool();
}
__declspec(dllexport) int native_metrics(Id* output) {
    if(!output)return 0;
    std::lock_guard<std::mutex> guard(metricsMutex);
    for(int i=0;i<2;i++) {
        auto& m=metrics[i];output[i*5]=m.uploads;output[i*5+1]=m.lastUpload;
        output[i*5+2]=m.submits;output[i*5+3]=m.lastSubmit;output[i*5+4]=m.copyNs;
    }
    output[10]=poolCount.load();output[11]=nodeCount[0].load()+nodeCount[1].load();return 1;
}
__declspec(dllexport) int native_output_samples(Id since, OutputSample* output, unsigned capacity) {
    if(!output)return 0;
    std::lock_guard<std::mutex> guard(metricsMutex);
    unsigned count=0;
    while(count<capacity && count<sampleCapacity && count<outputSampleCount){
        auto sample=outputSamples[(outputSampleCount-1-count)%sampleCapacity];
        if(sample.endNs<since)break;
        output[count++]=sample;
    }
    return int(count);
}
}
#include "qt_native_delivery.moc"
