// Standalone public-video producer extension, not loaded by the live app.
#include "live_texture_projection.cu"
#include <tlhelp32.h>

extern "C" __declspec(dllexport) int live_texture_export(void* value,unsigned long parentId,
    unsigned long long* handles,unsigned long* low,long* high) {
    HANDLE parent=nullptr;HANDLE exported[2]={};
    try {
        auto* texture=static_cast<ProjectionTexture*>(value);texture->check();
        if(!handles || !low || !high)throw std::runtime_error("Missing descriptor output");
        HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
        if(snapshot==INVALID_HANDLE_VALUE)throw std::runtime_error("Parent snapshot failed");
        PROCESSENTRY32 entry={};entry.dwSize=sizeof(entry);bool matched=false;
        if(Process32First(snapshot,&entry))do {
            if(entry.th32ProcessID==GetCurrentProcessId()){matched=entry.th32ParentProcessID==parentId;break;}
        }while(Process32Next(snapshot,&entry));CloseHandle(snapshot);
        if(!matched)throw std::runtime_error("Recipient is not actual parent");
        parent=OpenProcess(PROCESS_DUP_HANDLE,FALSE,parentId);
        if(!parent)throw std::runtime_error("Open parent failed");
        for(int i=0;i<2;i++) {
            ComPtr<IDXGIResource1> resource;hr(texture->slots[i].writer.As(&resource),"Export resource");
            HANDLE local=nullptr;hr(resource->CreateSharedHandle(nullptr,
                DXGI_SHARED_RESOURCE_READ|DXGI_SHARED_RESOURCE_WRITE,nullptr,&local),"Export handle");
            BOOL ok=DuplicateHandle(GetCurrentProcess(),local,parent,&exported[i],0,FALSE,DUPLICATE_SAME_ACCESS);
            CloseHandle(local);if(!ok)throw std::runtime_error("Duplicate into parent failed");
        }
        ComPtr<IDXGIDevice> dxgi;hr(texture->producer.As(&dxgi),"Producer DXGI");
        ComPtr<IDXGIAdapter> adapter;hr(dxgi->GetAdapter(&adapter),"Producer adapter");
        DXGI_ADAPTER_DESC desc={};hr(adapter->GetDesc(&desc),"Producer adapter desc");
        for(int i=0;i<2;i++)handles[i]=reinterpret_cast<unsigned long long>(exported[i]);
        *low=desc.AdapterLuid.LowPart;*high=desc.AdapterLuid.HighPart;
        CloseHandle(parent);return 1;
    } catch(const std::exception& e) {
        if(parent) {
            for(auto handle:exported)if(handle){HANDLE local=nullptr;if(DuplicateHandle(parent,handle,
                GetCurrentProcess(),&local,0,FALSE,DUPLICATE_SAME_ACCESS|DUPLICATE_CLOSE_SOURCE))CloseHandle(local);}
            CloseHandle(parent);
        }
        projection_texture_error=e.what();return 0;
    }
}
extern "C" __declspec(dllexport) int live_texture_publish(void* value,void* live,
    float convergence,float scale,int coverage,const float* refined,int index,int clear) {
    try {
        auto* texture=static_cast<ProjectionTexture*>(value);texture->check();
        auto* c=static_cast<LiveDepth*>(live);
        if(!c || c->w!=texture->w || c->h!=texture->h || index<0 || index>1 ||
            !std::isfinite(convergence) || !std::isfinite(scale) || scale<0 ||
            (coverage!=0 && coverage!=1) || (clear!=0 && clear!=1))throw std::runtime_error("Invalid publish descriptor");
        auto& slot=texture->slots[index];auto stream=c->stream;int blocks=(c->n+255)/256;
#ifdef DEPTHSBS_TEXTURE_TIMING
        CU(cudaEventRecord(c->events[7],stream));
#endif
        if(!clear) {
            int invalid=0;CU(cudaMemcpyAsync(&invalid,c->invalid,sizeof(invalid),cudaMemcpyDeviceToHost,stream));
            CU(cudaStreamSynchronize(stream));
            if(invalid)throw std::runtime_error("Non-finite raw depth");
            if(refined)CU(cudaMemcpyAsync(c->aligned,refined,c->n*4,cudaMemcpyHostToDevice,stream));
        }
        cudaExternalSemaphoreWaitParams wait={};wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        if(clear) {
            paint<<<dim3((texture->w*2+31)/32,(texture->h+7)/8),dim3(32,8),0,stream>>>(slot.surface,texture->w*2,texture->h,0,true);
        } else {
            make_shift<<<blocks,256,0,stream>>>(*c,convergence,scale);
#ifdef DEPTHSBS_TEXTURE_TIMING
            CU(cudaEventRecord(c->projection_events[0],stream));
#endif
            for(int eye=0;eye<2;eye++) {
                if(eye)negate_shift<<<blocks,256,0,stream>>>(c->shift,c->n);
                CU(cudaMemsetAsync(c->owners,0,c->n*8,stream));
                splat<<<blocks,256,0,stream>>>(c->aligned,c->shift,c->owners,c->w,c->n,coverage!=0);
#ifdef DEPTHSBS_TEXTURE_TIMING
                CU(cudaEventRecord(c->projection_events[eye*3+1],stream));
#endif
                if(c->parallel_resolve)launch_resolve_parallel(c->rgb,c->owners,c->output,c->w,c->h,stream);
                else resolve<<<(c->h+63)/64,64,0,stream>>>(c->rgb,c->owners,c->output,c->w,c->h);
#ifdef DEPTHSBS_TEXTURE_TIMING
                CU(cudaEventRecord(c->projection_events[eye*3+2],stream));
#endif
                pack_eye_surface<<<blocks,256,0,stream>>>(c->output,slot.surface,c->w,c->h,eye);
#ifdef DEPTHSBS_TEXTURE_TIMING
                CU(cudaEventRecord(c->projection_events[eye*3+3],stream));
#endif
            }
        }
        CU(cudaGetLastError());cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));
#ifdef DEPTHSBS_TEXTURE_TIMING
        CU(cudaEventRecord(c->events[8],stream));
#endif
        CU(cudaStreamSynchronize(stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int live_texture_readback(void* value,int index,unsigned char* diagnostic) {
    try {
        auto* texture=static_cast<ProjectionTexture*>(value);texture->check();
        if(index<0 || index>1 || !diagnostic)throw std::runtime_error("Invalid readback descriptor");
        auto& slot=texture->slots[index];auto* context=texture->context.Get();
        hr(slot.reader_mutex->AcquireSync(1,2000),"Oracle acquire");slot.reader_locked=true;
        context->CopyResource(slot.staging.Get(),slot.reader.Get());D3D11_MAPPED_SUBRESOURCE mapped={};
        hr(context->Map(slot.staging.Get(),0,D3D11_MAP_READ,0,&mapped),"Oracle map");
        for(int y=0;y<texture->h;y++)memcpy(diagnostic+static_cast<size_t>(y)*texture->w*8,
            static_cast<unsigned char*>(mapped.pData)+static_cast<size_t>(y)*mapped.RowPitch,texture->w*8);
        context->Unmap(slot.staging.Get(),0);hr(slot.reader_mutex->ReleaseSync(0),"Oracle release");slot.reader_locked=false;return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
extern "C" __declspec(dllexport) int live_texture_release(void* value,int index) {
    try {
        auto* texture=static_cast<ProjectionTexture*>(value);texture->check();
        if(index<0 || index>1)throw std::runtime_error("Invalid release descriptor");
        auto& slot=texture->slots[index];
        hr(slot.reader_mutex->AcquireSync(1,2000),"Diagnostic acquire");slot.reader_locked=true;
        hr(slot.reader_mutex->ReleaseSync(0),"Diagnostic release");slot.reader_locked=false;return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
