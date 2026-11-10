// Opt-in RowFlow bridge; borrows the pinned LiveDepth layout, never replaces it.
#include "live_texture_runtime.cu"

extern "C" __declspec(dllexport) int rowflow_copy_inputs(void* live,
    unsigned char* rgb,float* depth,const float* refined,int* invalid) {
    try {
        auto* c=static_cast<LiveDepth*>(live);
        if(!c || !rgb || !depth || !invalid)throw std::runtime_error("Invalid RowFlow input buffers");
        if(refined)CU(cudaMemcpyAsync(c->aligned,refined,c->n*4,cudaMemcpyHostToDevice,c->stream));
        CU(cudaMemcpyAsync(rgb,c->rgb,c->n*3,cudaMemcpyDeviceToDevice,c->stream));
        CU(cudaMemcpyAsync(depth,c->aligned,c->n*4,cudaMemcpyDeviceToDevice,c->stream));
        CU(cudaMemcpyAsync(invalid,c->invalid,4,cudaMemcpyDeviceToHost,c->stream));
        CU(cudaStreamSynchronize(c->stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}
__global__ void rowflow_pack(const unsigned char* rgb,cudaSurfaceObject_t surface,int w,int h) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=w*h)return;
    surf2Dwrite(make_uchar4(rgb[i*3],rgb[i*3+1],rgb[i*3+2],255),surface,(i%w)*4,i/w);
}
extern "C" __declspec(dllexport) int rowflow_publish(void* value,const unsigned char* rgb,
    int w,int h,int index,void* stream_value) {
    try {
        auto* pool=static_cast<OwnedTexturePool*>(value);
        if(!pool || !rgb || !stream_value || index<0 || index>1)
            throw std::runtime_error("Invalid RowFlow output descriptor");
        auto* texture=pool->texture.get();texture->check();
        if(w!=texture->w*2 || h!=texture->h)throw std::runtime_error("RowFlow output size mismatch");
        auto stream=static_cast<cudaStream_t>(stream_value);auto& slot=texture->slots[index];
        cudaExternalSemaphoreWaitParams wait={};wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        for(int eye=0;eye<2;eye++)
            pack_eye_surface<<<(w*h/2+255)/256,256,0,stream>>>(rgb+eye*(w/2)*3,slot.surface,w/2,h,eye,texture->layout,w);
        CU(cudaGetLastError());cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));
        CU(cudaStreamSynchronize(stream));return 1;
    }catch(const std::exception& e){projection_texture_error=e.what();return 0;}
}

// One unnamed job handle, owned until worker process exit. If its GUI terminates
// that worker during synchronous compilation, Windows closes the handle and
// terminates only this job's compiler descendants. Never call in the GUI process.
extern "C" __declspec(dllexport) int rowflow_protect_worker() {
    static HANDLE job=nullptr;
    if(job)return 1;
    HANDLE candidate=CreateJobObjectW(nullptr,nullptr);
    if(!candidate){projection_texture_error="Create compiler job failed";return 0;}
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits={};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if(!SetInformationJobObject(candidate,JobObjectExtendedLimitInformation,&limits,sizeof(limits)) ||
       !AssignProcessToJobObject(candidate,GetCurrentProcess())) {
        CloseHandle(candidate);projection_texture_error="Assign compiler worker job failed";return 0;
    }
    job=candidate;return 1;
}
