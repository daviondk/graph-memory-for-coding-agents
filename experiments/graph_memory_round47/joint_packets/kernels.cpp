#include <algorithm>
#include <cstdint>
#include <vector>
#ifdef _WIN32
#define ENTRY extern "C" __declspec(dllexport)
#else
#define ENTRY extern "C"
#endif
using I = int64_t;
using Bytes = uint8_t;

// Rank-ordered strict updates implement the same tie preference as the offline index.
ENTRY int packet2(int n, int cap, const int* cost, const I* value, const Bytes* mark,
                  I x, I y, const uint16_t* head, int h, const uint16_t* ids, uint16_t* result) {
    static thread_local std::vector<I> d;
    static thread_local std::vector<Bytes> take;
    d.assign(cap+1,0);take.resize(size_t(n)*(cap+1));
    for(int i=0;i<n;++i) {
        const int c=cost[i];const I v=value[i]+(mark[i]&1?x:0)+(mark[i]&2?y:0);
        Bytes* row=take.data()+size_t(i)*(cap+1);
        for(int w=cap;w>=c;--w) {
            const I with=d[w-c]+v;row[w]=with>d[w]; if(row[w]) d[w]=with;
        }
    }
    int out=h;
    std::copy_n(head,h,result);
    int left=cap;
    for(int i=n-1;i>=0;--i) {
        if(cost[i]<=left && take[size_t(i)*(cap+1)+left]) {result[out++]=ids[i];left-=cost[i];}
    }
    std::reverse(result+h,result+out);
    return out;
}

// Solve unmarked items once, then reconstruct the preferred complement at each requested capacity.
ENTRY void complements(int n, int cap, const int* cost, const I* value, const Bytes* mark,
                       int num, const int* capacities, I* totals, Bytes* output) {
    std::vector<I> best(cap+1,0);
    std::vector<Bytes> take(size_t(n)*(cap+1),0);
    for(int i=0;i<n;++i) if(mark[i]==0) {
        for(int w=cap;w>=cost[i];--w) {
            I with=best[w-cost[i]]+value[i];
            if(with>best[w]) {take[size_t(i)*(cap+1)+w]=1;best[w]=with;}
        }
    }
    int width=(n+7)/8;
    for(int j=0;j<num;++j) {
        int left=capacities[j];totals[j]=best[left];
        auto* mask=output+size_t(j)*width;
        std::fill(mask,mask+width,0);
        for(int i=n-1;i>=0;--i) if(take[size_t(i)*(cap+1)+left]) {
            mask[i/8]|=Bytes(1<<(i%8));left-=cost[i];
        }
    }
}
