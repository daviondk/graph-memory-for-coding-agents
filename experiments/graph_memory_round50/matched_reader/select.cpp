// Upstream R40 and R49 kernels are preserved verbatim. Select accepts the same arrays in every mode.
#include "guard.cpp"
#ifdef _WIN32
#include "kernels.cpp"
#else
#define __declspec(x)
#include "kernels.cpp"
#endif

EXPORT int packet(int n,int mode,int convention,const int* order,const int* costs,const double* gain,int* out) {
    if(mode==0) return pack(n,2048,3,order,costs,gain,out); // Original reader.
    if(mode==3) return pack(n,2048,0,order,costs,nullptr,out);
    if(mode==4 && convention==0) return pack(n,2048,1,order,costs,gain,out);
    if(mode==4){
        int j=0,k=0,used=0;
        while(j<n && used+costs[order[j]]<=1024){out[k++]=order[j];used+=costs[order[j++]];}
        std::vector<int> tail(order+j,order+n);
        std::stable_sort(tail.begin(),tail.end(),[&](int a,int b){return gain[a]>gain[b];});
        for(int id:tail)if(used+costs[id]<=2048){out[k++]=id;used+=costs[id];}
        return k;
    }
    // Linear-time rearrangement and (only for the guarded plan) quantization are inside the timer.
    std::vector<double> ordered(n);
    std::vector<I> fixed(n);
    for(int j=0;j<n;++j){
        ordered[j]=gain[order[j]];
        if(mode==1) fixed[j]=I(std::nearbyint(std::ldexp(ordered[j],32)));
    }
    int endOut=0;I stats[3]={};
    return solve(n,1,2048,1024,mode==1,&n,order,costs,fixed.data(),ordered.data(),&endOut,out,stats);
}
