#define NOMINMAX
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <QtCore/QProcess>
#include <QtCore/QCoreApplication>
#include <QtCore/QElapsedTimer>
#include <chrono>
#include <thread>
#include <stdexcept>
#include <string>
#include <cstdio>
#include <atomic>
using Microsoft::WRL::ComPtr;
static void hr(HRESULT value,const char* label) {
    if(value!=S_OK)throw std::runtime_error(std::string(label)+": "+std::to_string(value));
}
struct OwnedChild:QProcess {
    ~OwnedChild() override {
        if(state()!=NotRunning) {
            write("STOP\n");waitForBytesWritten(500);
            if(!waitForFinished(3000)){kill();waitForFinished(3000);}
        }
    }
};
struct IpcSource {
    OwnedChild child;
    ComPtr<ID3D11Texture2D> textures[2];
    ComPtr<IDXGIKeyedMutex> mutexes[2];
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11Query> completion;
    std::thread::id owner=std::this_thread::get_id();
    int active=-1;
    QByteArray receive(int timeout) {
        QElapsedTimer elapsed;elapsed.start();
        while(!child.canReadLine()) {
            if(child.bytesAvailable()>512)throw std::runtime_error("Oversized child message");
            int remaining=timeout-static_cast<int>(elapsed.elapsed());
            if(remaining<=0 || !child.waitForReadyRead(remaining))
                throw std::runtime_error("Child response failed: "+child.readAllStandardError().toStdString());
        }
        auto line=child.readLine(513);
        if(line.size()>512 || !line.endsWith('\n'))throw std::runtime_error("Invalid child message length");
        return line.replace("\r\n","\n");
    }
    IpcSource(ID3D11Device* device,int w,int h) {
        if(!device || w<1 || h<1 || w>8192 || h>4320)throw std::runtime_error("Invalid descriptor");
        ComPtr<ID3D11Device1> device1;hr(device->QueryInterface(IID_PPV_ARGS(&device1)),"Qt device1");
        ComPtr<IDXGIDevice> dxgi;hr(device->QueryInterface(IID_PPV_ARGS(&dxgi)),"Qt DXGI device");
        ComPtr<IDXGIAdapter> adapter;hr(dxgi->GetAdapter(&adapter),"Qt adapter");
        DXGI_ADAPTER_DESC adapterDesc={};hr(adapter->GetDesc(&adapterDesc),"Qt adapter desc");
        device->GetImmediateContext(&context);
        D3D11_QUERY_DESC query={D3D11_QUERY_EVENT,0};hr(device->CreateQuery(&query,&completion),"GPU query");
        child.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments* args){args->flags|=CREATE_NO_WINDOW;});
        QStringList args={QString::number(GetCurrentProcessId()),QString::number(w),QString::number(h)};
        if(qEnvironmentVariableIsSet("SCREENTO3D_TEXTURE_PUBLIC") || qEnvironmentVariableIsSet("STEREOTO3D_TEXTURE_PUBLIC") || qEnvironmentVariableIsSet("DEPTHSBS_TEXTURE_PUBLIC")) {
            args.prepend(QCoreApplication::applicationDirPath()+"/../../v1/texture_public_worker.py");
            const QString interpreter=qEnvironmentVariableIsSet("SCREENTO3D_TEXTURE_PYTHON")
                ? qEnvironmentVariable("SCREENTO3D_TEXTURE_PYTHON")
                : qEnvironmentVariableIsSet("STEREOTO3D_TEXTURE_PYTHON") ? qEnvironmentVariable("STEREOTO3D_TEXTURE_PYTHON") : qEnvironmentVariable("DEPTHSBS_TEXTURE_PYTHON");
            if(interpreter.isEmpty())throw std::runtime_error("Missing explicit test interpreter");
            child.start(interpreter,args);
        } else {
            child.start(QCoreApplication::applicationDirPath()+"/qt_texture_worker.exe",args);
        }
        if(!child.waitForStarted(3000))throw std::runtime_error("Owned child startup failed");
        auto line=receive(10000);
        int receivedW=0,receivedH=0;unsigned long low=0;long high=0;
        unsigned long long handles[2]={};char trailing=0;
        if(std::sscanf(line.constData(),"READY %d %d %lu %ld %llu %llu %c",&receivedW,&receivedH,
            &low,&high,&handles[0],&handles[1],&trailing)!=6)throw std::runtime_error("Invalid ready descriptor");
        struct ImportedHandles {
            HANDLE values[2];
            ~ImportedHandles(){for(auto value:values)if(value)CloseHandle(value);}
        } imported{{reinterpret_cast<HANDLE>(handles[0]),reinterpret_cast<HANDLE>(handles[1])}};
        if(receivedW!=w || receivedH!=h || low!=adapterDesc.AdapterLuid.LowPart || high!=adapterDesc.AdapterLuid.HighPart)
            throw std::runtime_error("Child descriptor/adapter mismatch");
        for(int i=0;i<2;i++) {
            hr(device1->OpenSharedResource1(imported.values[i],IID_PPV_ARGS(&textures[i])),"Open child texture");
            D3D11_TEXTURE2D_DESC desc={};textures[i]->GetDesc(&desc);
            if(desc.Width!=w || desc.Height!=h || desc.Format!=DXGI_FORMAT_R8G8B8A8_UNORM ||
                desc.MipLevels!=1 || desc.ArraySize!=1 || desc.SampleDesc.Count!=1 ||
                !(desc.MiscFlags&D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX))
                throw std::runtime_error("Invalid imported texture");
            hr(textures[i].As(&mutexes[i]),"Child texture mutex");
        }
    }
    void check(){if(owner!=std::this_thread::get_id())throw std::runtime_error("Wrong consumer thread");}
    void begin(int index,int frame,bool clear) {
        check();if(active!=-1)end();
        if(index<0 || index>1 || frame<0)throw std::runtime_error("Invalid frame request");
        QByteArray command="FRAME "+QByteArray::number(index)+" "+QByteArray::number(frame)+" "+QByteArray::number(clear?1:0)+"\n";
        if(child.write(command)!=command.size() || !child.waitForBytesWritten(1000))throw std::runtime_error("Child write failed");
        auto reply=receive(3000);
        if(reply!="FRAME "+QByteArray::number(index)+" "+QByteArray::number(frame)+"\n")throw std::runtime_error("Frame acknowledgement mismatch");
        hr(mutexes[index]->AcquireSync(1,2000),"Acquire child texture");active=index;
    }
    void end() {
        check();if(active==-1)return;
        context->End(completion.Get());context->Flush();
        auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);BOOL done=FALSE;
        while(true) {
            HRESULT result=context->GetData(completion.Get(),&done,sizeof(done),0);
            if(result==S_OK && done)break;
            if(result!=S_OK && result!=S_FALSE)hr(result,"Consumer completion");
            if(std::chrono::steady_clock::now()>deadline)throw std::runtime_error("Consumer completion timeout");
            std::this_thread::yield();
        }
        hr(mutexes[active]->ReleaseSync(0),"Release child texture");active=-1;
    }
    void close() {
        check();end();child.write("STOP\n");child.waitForBytesWritten(500);
        if(!child.waitForFinished(3000))throw std::runtime_error("Owned child stop timeout");
        if(child.exitStatus()!=QProcess::NormalExit || child.exitCode()!=0)throw std::runtime_error("Owned child failed on close");
        if(child.readAllStandardOutput().replace("\r\n","\n")!="STOPPED\n")throw std::runtime_error("Missing child cleanup confirmation");
    }
};
static thread_local std::string lastError;
static std::atomic<int> live_sources{0},created_sources{0},closed_sources{0};
#define EXPORT extern "C" __declspec(dllexport)
EXPORT void texture_counts(int* live,int* created,int* closed) {
    *live=live_sources.load();*created=created_sources.load();*closed=closed_sources.load();
}
EXPORT const char* texture_last_error(){return lastError.c_str();}
EXPORT void* texture_create(void* device,int w,int h) {
    try{auto* source=new IpcSource(static_cast<ID3D11Device*>(device),w,h);live_sources++;created_sources++;return source;}
    catch(const std::exception& e){lastError=e.what();return nullptr;}
}
EXPORT void* texture_handle(void* source,int index) {
    if(!source || index<0 || index>1)return nullptr;
    return static_cast<IpcSource*>(source)->textures[index].Get();
}
EXPORT int texture_begin(void* source,int index,int frame,int clear) {
    try{static_cast<IpcSource*>(source)->begin(index,frame,clear!=0);return 1;}
    catch(const std::exception& e){lastError=e.what();return 0;}
}
EXPORT int texture_end(void* source) {
    try{static_cast<IpcSource*>(source)->end();return 1;}
    catch(const std::exception& e){lastError=e.what();return 0;}
}
EXPORT int texture_destroy(void* value) {
    auto* source=static_cast<IpcSource*>(value);
    try{source->close();delete source;live_sources--;closed_sources++;return 1;}
    catch(const std::exception& e){lastError=e.what();delete source;return 0;}
}
