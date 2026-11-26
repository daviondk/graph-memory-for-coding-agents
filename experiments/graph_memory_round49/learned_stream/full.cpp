#include <algorithm>
#include <cstdint>
#include <vector>
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
extern "C" EXPORT void pick(int n,int cap,const int* cost,const int64_t* utility,unsigned char* selected) {
    std::vector<int64_t> dp(cap+1,0);
    std::vector<unsigned char> take((cap+1)*n,0);
    for(int i=0;i<n;++i){
        for(int w=cap;w>=cost[i];--w){
            auto trial=dp[w-cost[i]]+utility[i];
            if(trial>dp[w]){ dp[w]=trial;take[i*(cap+1)+w]=1; }
        }
    }
    int w=cap;
    for(int i=n-1;i>=0;--i){
        selected[i]=take[i*(cap+1)+w];
        if(selected[i]) w-=cost[i];
    }
}
