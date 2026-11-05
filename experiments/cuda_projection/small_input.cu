// OpenCV-derived thumbnail and notice are included from base_input.cu.
// Small uses uint8 cubic resize BEFORE float32 normalization. Shape-only IPP
// coefficients are prepared once; no captured pixels visit CPU preprocessing.
// LiveDepth layout remains unchanged for borrowed native output.
#include "live_depth.cu"
#include "base_input.cu"

__global__ void small_resize_kernel(const unsigned char* rgb,size_t pitch,int w,int h,
    int channels,unsigned char* dst,const float* coefficients) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=518*518*3)return;
    int c=i%3,x=(i/3)%518,y=i/(518*3),channel=channels==4?2-c:c;
    if(w==518&&h==518){dst[i]=rgb[y*pitch+x*channels+channel];return;}
    int sx=int(floor((x+.5)*(double(w)/518)-.5));
    int sy=int(floor((y+.5)*(double(h)/518)-.5));
    const float* ax=coefficients+x*4;
    const float* ay=coefficients+(518+y)*4;
    float rows[4];
    for(int j=0;j<4;j++){
        float row=0;
        // IPP's clamped left-edge accumulation runs in the opposite order
        // from its interior horizontal loop. Preserve the rounding boundary.
        for(int tap=0;tap<4;tap++){
            int k=sx<1?3-tap:tap;
            float pixel=rgb[size_t(min(max(sy+j-1,0),h-1))*pitch+min(max(sx+k-1,0),w-1)*channels+channel];
            row=__fmaf_rn(pixel,ax[k],row);
        }
        rows[j]=row;
    }
    float result=__fmaf_rn(rows[0],ay[0],rows[1]*ay[1])+__fmaf_rn(rows[2],ay[2],rows[3]*ay[3]);
    dst[i]=(unsigned char)min(max(__float2int_rn(result),0),255);
}
extern "C" __declspec(dllexport) int small_resize(const unsigned char* rgb,size_t pitch,
    int w,int h,int channels,unsigned char* out,void* stream,const float* coefficients) {
    if(!rgb||!out||!stream||!coefficients||w<16||w>4096||h<16||h>2160||
        (channels!=3&&channels!=4)||pitch<size_t(w*channels))return 1;
    small_resize_kernel<<<(518*518*3+255)/256,256,0,(cudaStream_t)stream>>>(rgb,pitch,w,h,channels,out,coefficients);
    return int(cudaGetLastError());
}
extern "C" __declspec(dllexport) int small_prepare(void* handle,const unsigned char* rgb,
    size_t pitch,int w,int h,float* out,const float* coefficients) {
    auto c=(LiveDepth*)handle;if(!c||!out||w!=c->w||h!=c->h)return 1;
    auto e=cudaEventRecord(c->events[0],c->stream);if(e!=cudaSuccess)return int(e);
    int status=small_resize(rgb,pitch,w,h,3,c->small_rgb,c->stream,coefficients);
    if(status)return status;
    input_normalize<<<(518*518+255)/256,256,0,c->stream>>>(c->small_rgb,out);
    e=cudaGetLastError();if(e==cudaSuccess)e=cudaEventRecord(c->events[1],c->stream);
    return int(e);
}
