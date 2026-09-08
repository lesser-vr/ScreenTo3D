// Owned synthetic producer for the cross-process Qt boundary experiment.
#define DEPTHSBS_TEXTURE_LIBRARY
#include "texture_handoff_probe.cu"
#include <tlhelp32.h>

int main(int argc,char** argv) {
    HANDLE parent=nullptr;cudaStream_t stream=nullptr;
    HANDLE exported[2]={};bool published=false;
    try {
        if(argc!=4)throw std::runtime_error("Expected parent PID, width, height");
        DWORD parentId=static_cast<DWORD>(std::stoul(argv[1]));
        int w=std::stoi(argv[2]),h=std::stoi(argv[3]);
        if(w<1 || h<1 || w>8192 || h>4320)throw std::runtime_error("Invalid dimensions");
        HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
        if(snapshot==INVALID_HANDLE_VALUE)throw std::runtime_error("Process snapshot failed");
        PROCESSENTRY32 entry={};entry.dwSize=sizeof(entry);bool matched=false;
        if(Process32First(snapshot,&entry))do {
            if(entry.th32ProcessID==GetCurrentProcessId()) {
                matched=entry.th32ParentProcessID==parentId;break;
            }
        }while(Process32Next(snapshot,&entry));
        CloseHandle(snapshot);
        if(!matched)throw std::runtime_error("Handle recipient is not actual parent");
        parent=OpenProcess(PROCESS_DUP_HANDLE,FALSE,parentId);
        if(!parent)throw std::runtime_error("Open actual parent failed");
        int cudaDevice=0;CU(cudaGetDevice(&cudaDevice));cudaDeviceProp prop={};
        CU(cudaGetDeviceProperties(&prop,cudaDevice));
        ComPtr<IDXGIFactory1> factory;hr(CreateDXGIFactory1(IID_PPV_ARGS(&factory)),"DXGI factory");
        ComPtr<IDXGIAdapter1> adapter;DXGI_ADAPTER_DESC1 selected={};
        for(UINT i=0;;i++) {
            ComPtr<IDXGIAdapter1> candidate;
            HRESULT result=factory->EnumAdapters1(i,&candidate);
            if(result==DXGI_ERROR_NOT_FOUND)break;hr(result,"EnumAdapters1");
            DXGI_ADAPTER_DESC1 desc={};hr(candidate->GetDesc1(&desc),"Adapter desc");
            if(!memcmp(&desc.AdapterLuid,prop.luid,sizeof(LUID))){adapter=candidate;selected=desc;break;}
        }
        if(!adapter)throw std::runtime_error("CUDA adapter not found");
        ComPtr<ID3D11Device> device;
        hr(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,
            D3D11_SDK_VERSION,&device,nullptr,nullptr),"Producer device");
        ComPtr<ID3D11Device1> device1;hr(device.As(&device1),"Device1");
        Slot slots[2];
        for(int i=0;i<2;i++) {
            slots[i].create(device.Get(),device1.Get(),w,h,false);
            ComPtr<IDXGIResource1> resource;hr(slots[i].writer.As(&resource),"Export resource");
            HANDLE local=nullptr;
            hr(resource->CreateSharedHandle(nullptr,DXGI_SHARED_RESOURCE_READ|DXGI_SHARED_RESOURCE_WRITE,
                nullptr,&local),"Export NT handle");
            BOOL ok=DuplicateHandle(GetCurrentProcess(),local,parent,&exported[i],0,FALSE,DUPLICATE_SAME_ACCESS);
            CloseHandle(local);if(!ok)throw std::runtime_error("Duplicate into parent failed");
        }
        CU(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
        std::printf("READY %d %d %lu %ld %llu %llu\n",w,h,selected.AdapterLuid.LowPart,
            selected.AdapterLuid.HighPart,reinterpret_cast<unsigned long long>(exported[0]),
            reinterpret_cast<unsigned long long>(exported[1]));std::fflush(stdout);
        published=true;CloseHandle(parent);parent=nullptr;
        char line[256];
        int commands=0;
        while(std::fgets(line,sizeof(line),stdin)) {
            if(std::string(line)=="STOP\n")break;
            int index=-1,frame=-1,clear=-1;char trailing=0;
            if(std::sscanf(line,"FRAME %d %d %d %c",&index,&frame,&clear,&trailing)!=3 ||
                index<0 || index>1 || frame<0 || (clear!=0 && clear!=1))
                throw std::runtime_error("Invalid frame command");
            // Explicit fault injection in this standalone executable only.
            if(std::getenv("DEPTHSBS_TEXTURE_TEST_CRASH") && ++commands==10)
                TerminateProcess(GetCurrentProcess(),42);
            auto& slot=slots[index];cudaExternalSemaphoreWaitParams wait={};
            wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
            CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
            paint<<<dim3((w+31)/32,(h+7)/8),dim3(32,8),0,stream>>>(slot.surface,w,h,frame,clear!=0);
            CU(cudaGetLastError());cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
            CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));
            CU(cudaStreamSynchronize(stream));
            std::printf("FRAME %d %d\n",index,frame);std::fflush(stdout);
        }
        CU(cudaStreamSynchronize(stream));for(auto& slot:slots)slot.close();
        CU(cudaStreamDestroy(stream));stream=nullptr;
        std::puts("STOPPED");std::fflush(stdout);return 0;
    } catch(const std::exception& e) {
        if(parent && !published)for(auto handle:exported)if(handle) {
            HANDLE recovered=nullptr;
            if(DuplicateHandle(parent,handle,GetCurrentProcess(),&recovered,0,FALSE,
                DUPLICATE_SAME_ACCESS|DUPLICATE_CLOSE_SOURCE))CloseHandle(recovered);
        }
        if(parent)CloseHandle(parent);
        if(stream){cudaStreamSynchronize(stream);cudaStreamDestroy(stream);}
        std::fprintf(stderr,"Worker failed: %s\n",e.what());return 1;
    }
}
