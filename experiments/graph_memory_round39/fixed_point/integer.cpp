#include <cstdint>
#include <vector>
extern "C" __declspec(dllexport) void choose64(int n,int capacity,const int32_t* cost,
        const int64_t* gain,uint8_t* selected) {
    std::vector<int64_t> dp(capacity+1,0);
    std::vector<uint8_t> take(static_cast<size_t>(n)*(capacity+1),0);
    for (int i=0; i<n; ++i) {
        for (int j=capacity; j>=cost[i]; --j) {
            int64_t alt=dp[j-cost[i]]+gain[i];
            if (alt>dp[j]) {dp[j]=alt;take[static_cast<size_t>(i)*(capacity+1)+j]=1;}
        }
    }
    int j=capacity;
    for (int i=n-1; i>=0; --i) {
        selected[i]=take[static_cast<size_t>(i)*(capacity+1)+j];
        if (selected[i]) j-=cost[i];
    }
}
