// Exact floating expansion experiment. Parity passed; slower on RTX 5090.
// Not used by the product. See gpu-load-optimization-20261106 evidence.
struct GuideSum {
    float hi=0,lo=0;int low=255,high=0;bool slow=false;double precise=0;
    __device__ void add(float value) {
        if(slow){precise+=double(value);return;}
        unsigned bits=__float_as_uint(value)&0x7fffffffu;
        if(!bits)return;
        int exponent=int(bits>>23),next_low=min(low,exponent),next_high=max(high,exponent);
        if(exponent==0 || next_high>250 || next_high-next_low>12) {
            precise=double(hi)+double(lo);precise+=double(value);slow=true;return;
        }
        low=next_low;high=next_high;
        float sum=__fadd_rn(hi,value),back=__fsub_rn(sum,hi);
        float error=__fadd_rn(__fsub_rn(hi,__fsub_rn(sum,back)),__fsub_rn(value,back));
        lo=__fadd_rn(lo,error);hi=sum;
    }
    __device__ double value() const {return slow?precise:double(hi)+double(lo);}
};
