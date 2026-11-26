// Exact integer utilities and a fixed total preference on complete ranked packets.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <limits>
#include <vector>

using I = int64_t;
const I UNREACHABLE = -(I(1)<<60);
const I INF = I(1)<<55;
#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif

// This routine sees the optional suffix only. Iterating ranks forward and
// updating strictly on gain prefers absence at the last differing rank.
EXPORT void full_select(int n, int cap, const int* cost, const I* utility,
                        const uint8_t* marked, I shift, uint8_t* chosen) {
    const int width=cap+1;
    std::vector<I> value(width,0);
    std::vector<uint8_t> take(size_t(n)*width,0);
    for(int i=0;i<n;++i) {
        I profit=utility[i]+(marked[i]?shift:0);
        for(int b=cap;b>=cost[i];--b) {
            I proposed=value[b-cost[i]]+profit;
            if(proposed>value[b]) {
                value[b]=proposed;
                take[size_t(i)*width+b]=1;
            }
        }
    }
    int left=cap;
    for(int i=n-1;i>=0;--i) {
        chosen[i]=take[size_t(i)*width+left];
        if(chosen[i]) left-=cost[i];
    }
}

// O(n*B + m^2*B) direct implementation; m marks the feasible suffix items of that source.
// The first and last allowed shifts include ties only if the cached packet wins them.
EXPORT void interval(int n, int cap, const int* cost, const I* utility,
                     const uint8_t* mark, const uint8_t* old, I* answer) {
    const int width=cap+1;
    int m=0, old_count=0;
    I old_value=0;
    for(int i=0;i<n;++i) {
        if(mark[i] && cost[i]<=cap) ++m;
        if(old[i]) {old_count+=mark[i];old_value+=utility[i];}
    }
    std::vector<I> dp(size_t(m+1)*width,UNREACHABLE);
    std::fill(dp.begin(),dp.begin()+width,0);
    for(int i=0;i<n;++i) if(!mark[i]) {
        for(int b=cap;b>=cost[i];--b) {
            dp[b]=std::max(dp[b],dp[b-cost[i]]+utility[i]);
        }
    }
    int seen=0;
    for(int i=0;i<n;++i) if(mark[i] && cost[i]<=cap) {
        ++seen;
        for(int k=seen;k>0;--k) {
            I* row=dp.data()+size_t(k)*width;
            I* prev=row-width;
            for(int b=cost[i];b<=cap;++b) {
                I base=prev[b-cost[i]];
                if(base!=UNREACHABLE) row[b]=std::max(row[b],base+utility[i]);
            }
        }
    }
    if(dp[size_t(old_count)*width+cap]!=old_value) {answer[4]=1;return;}
    I lo=-INF,hi=INF;
    bool tie_lo=false, tie_hi=false;
    for(int k=0;k<=m;++k) {
        I val=dp[size_t(k)*width+cap];
        if(k==old_count || val==UNREACHABLE) continue;
        I gap=old_value-val;
        int dist=std::abs(k-old_count);
        I step=gap/dist;
        bool same=(gap%dist==0);
        if(k<old_count) {
            if(-step>lo) {lo=-step;tie_lo=same;}
            else if(-step==lo) tie_lo|=same;
        } else {
            if(step<hi) {hi=step;tie_hi=same;}
            else if(step==hi) tie_hi|=same;
        }
    }
    std::vector<uint8_t> packet(n,0);
    auto survives=[&](I s) {
        full_select(n,cap,cost,utility,mark,s,packet.data());
        return std::equal(packet.begin(),packet.end(),old);
    };
    if(tie_lo && !survives(lo)) ++lo;
    if(tie_hi && !survives(hi)) --hi;
    answer[0]=lo;answer[1]=hi;answer[2]=tie_lo;answer[3]=tie_hi;answer[4]=0;
}
