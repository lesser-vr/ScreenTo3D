#pragma once
// Guided filtering has finished and make_shift has consumed contour scratch.
// These arrays are fully overwritten by the next postprocessing call on the
// same stream. Persistent RGB/depth/range/motion/window histories stay intact.
static LiveDepth reduced_view(const LiveDepth& full,int layout) {
    LiveDepth view=full;
    view.w=layout==1?(full.w+1)/2:full.w;
    view.h=layout==3?(full.h+1)/2:full.h;
    view.n=view.w*view.h;
    view.rgb=reinterpret_cast<unsigned char*>(full.t1);
    view.aligned=full.t2;view.shift=full.t3;
    view.window_state=full.b;
    return view;
}
__global__ void reduce_stereo(LiveDepth source,LiveDepth target,int layout,int edge_aware) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=target.n)return;
    int x=i%target.w,y=i/target.w;
    int sx=layout==1?2*x:x,sy=layout==3?2*y:y;
    int a=sy*source.w+sx;
    int b=(layout==3?min(sy+1,source.h-1):sy)*source.w+
          (layout==1?min(sx+1,source.w-1):sx);
    float za=source.aligned[a],zb=source.aligned[b];
    bool boundary=edge_aware && fabsf(za-zb)>.04f;
    int foreground=za>=zb?a:b;
    for(int k=0;k<3;k++)
        target.rgb[i*3+k]=boundary?source.rgb[foreground*3+k]:
            (int(source.rgb[a*3+k])+source.rgb[b*3+k]+1)/2;
    target.aligned[i]=boundary?source.aligned[foreground]:(za+zb)*.5f;
    float shift=boundary?source.shift[foreground]:(source.shift[a]+source.shift[b])*.5f;
    target.shift[i]=shift*(layout==1?.5f:1.f);
    if(i<4)target.window_state[i]=source.window_state[i]*(layout==1?.5f:1.f);
}

static int publish_reduced_half(ProjectionTexture* texture,LiveDepth* full,
    float convergence,float scale,int coverage,const float* refined,int index,int edge_aware) {
        auto view=reduced_view(*full,texture->layout);
        auto stream=full->stream;
        CU(cudaEventRecord(full->events[7],stream));
        int invalid=0;
        CU(cudaMemcpyAsync(&invalid,full->invalid,4,cudaMemcpyDeviceToHost,stream));
        CU(cudaStreamSynchronize(stream));
        if(invalid)throw std::runtime_error("Non-finite raw depth");
        if(refined)CU(cudaMemcpyAsync(full->aligned,refined,full->n*4,cudaMemcpyHostToDevice,stream));
        auto& slot=texture->slots[index];
        cudaExternalSemaphoreWaitParams wait={};
        wait.params.keyedMutex.key=0;wait.params.keyedMutex.timeoutMs=2000;
        CU(cudaWaitExternalSemaphoresAsync(&slot.semaphore,&wait,1,stream));
        CU(live_make_shift(full,convergence,scale));
        CU(cudaEventRecord(full->projection_events[0],stream));
        int blocks=(view.n+255)/256;
        reduce_stereo<<<blocks,256,0,stream>>>(*full,view,texture->layout,edge_aware);
        for(int eye=0;eye<2;eye++) {
            if(eye)negate_shift<<<blocks,256,0,stream>>>(view.shift,view.n);
            CU(cudaMemsetAsync(view.owners,0,view.n*8,stream));
            splat<<<blocks,256,0,stream>>>(view.aligned,view.shift,view.owners,view.w,view.n,coverage!=0);
            CU(cudaEventRecord(full->projection_events[eye*3+1],stream));
            if(view.parallel_resolve)launch_resolve_parallel(view.rgb,view.owners,view.output,view.w,view.h,stream);
            else resolve<<<(view.h+63)/64,64,0,stream>>>(view.rgb,view.owners,view.output,view.w,view.h);
            live_reconstruct(&view);
            live_mask_window(&view,eye);
            CU(cudaEventRecord(full->projection_events[eye*3+2],stream));
            pack_eye_surface<<<blocks,256,0,stream>>>(view.output,slot.surface,view.w,view.h,eye,texture->layout==1?0:2);
            CU(cudaEventRecord(full->projection_events[eye*3+3],stream));
        }
        CU(cudaGetLastError());
        cudaExternalSemaphoreSignalParams signal={};signal.params.keyedMutex.key=1;
        CU(cudaSignalExternalSemaphoresAsync(&slot.semaphore,&signal,1,stream));
        CU(cudaEventRecord(full->events[8],stream));CU(cudaStreamSynchronize(stream));
        return 1;
}
