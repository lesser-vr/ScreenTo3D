#include "live_depth.cu"
#include "guide_sum_candidate.cuh"
__global__ void probe_sum(const float* input,double* actual,double* expected,int count) {
    int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;
    GuideSum sum;double reference=0;
    for(int j=0;j<9;j++) {
        float v=input[i*9+j];sum.add(v);reference+=double(v);
        actual[i*9+j]=sum.value();expected[i*9+j]=reference;
    }
}
extern "C" __declspec(dllexport) int guide_sum_probe(const float* input,double* actual,double* expected,int count,cudaStream_t stream) {
    probe_sum<<<(count+255)/256,256,0,stream>>>(input,actual,expected,count);
    return int(cudaGetLastError());
}
