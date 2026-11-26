#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <vector>
#ifdef _WIN32
#define PUBLIC extern "C" __declspec(dllexport)
#else
#define PUBLIC extern "C"
#endif
using namespace std;
using clock_type = chrono::steady_clock;

struct Frontier {
    int capacity = 0, words = 0;
    vector<int64_t> values;
    vector<uint64_t> masks;

    void reset(int cap, int width) {
        capacity=cap;
        words=width;
        values.assign(cap+1,0);
        masks.assign(static_cast<size_t>(cap+1)*width,0);
    }

    void add(int id, int cost, int64_t value, bool monotone_order) {
        for (int cap=capacity; cap>=cost; --cap) {
            int64_t candidate=values[cap-cost]+value;
            if (candidate<values[cap] || (monotone_order && candidate==values[cap])) continue;
            const uint64_t* before=&masks[static_cast<size_t>(cap-cost)*words];
            uint64_t* current=&masks[static_cast<size_t>(cap)*words];
            int slot=id/64;
            uint64_t bit=uint64_t(1)<<(id%64);
            if (candidate==values[cap]) {
                bool smaller=false;
                for (int i=words-1;i>=0;--i) {
                    uint64_t new_word=before[i]|(i==slot?bit:0);
                    if (new_word!=current[i]) { smaller=new_word<current[i]; break; }
                }
                if (!smaller) continue;
            }
            memcpy(current,before,static_cast<size_t>(words)*sizeof(uint64_t));
            current[slot]|=bit;
            values[cap]=candidate;
        }
    }
};

static void standard(const vector<int>& suffix,const int32_t* cost,const int64_t* value,
                     int capacity,vector<int>& chosen) {
    vector<int64_t> dp(capacity+1,0);
    vector<uint8_t> take(static_cast<size_t>(capacity+1)*suffix.size(),0);
    for (size_t j=0;j<suffix.size();++j) {
        int id=suffix[j];
        for(int w=capacity;w>=cost[id];--w) {
            int64_t alt=dp[w-cost[id]]+value[id];
            if(alt>dp[w]) { dp[w]=alt; take[j*(capacity+1)+w]=1; }
        }
    }
    int w=capacity;
    size_t start=chosen.size();
    for(int j=static_cast<int>(suffix.size())-1;j>=0;--j) {
        int id=suffix[j];
        if(take[static_cast<size_t>(j)*(capacity+1)+w]) {
            chosen.push_back(id);
            w-=cost[id];
        }
    }
    reverse(chosen.begin()+start,chosen.end());
}

// Execute one whole stream. Modes: classic scratch solver, incremental, expanded-state scratch.
// Each row of the output is a stable ordered-result bit set (global order is increasing ID).
PUBLIC void replay(int n,int steps,int budget,const int32_t* cost,const int64_t* value,
                   const int32_t* arrival,int mode,uint64_t* output,int64_t* stats) {
    const int words=(n+63)/64;
    Frontier state;
    vector<int> last_head;
    vector<uint8_t> visible(n,0);
    vector<vector<int>> batches(steps);
    for(int i=0;i<n;++i) batches[arrival[i]].push_back(i);
    int peak=0,rebuild=0;
    auto begin=clock_type::now();
    for(int step=0;step<steps;++step) {
        for(int id:batches[step]) visible[id]=1;
        vector<int> head,suffix,chosen;
        bool prefix=true;
        int used=0;
        for(int id=0;id<n;++id) {
            if(!visible[id]) continue;
            if(prefix && used+cost[id]<=budget/2) {
                head.push_back(id); used+=cost[id];
            } else { prefix=false; suffix.push_back(id); }
        }
        int cap=budget-used;
        uint64_t* dst=output+static_cast<size_t>(step)*words;
        fill(dst,dst+words,0);
        if(mode==0) {
            chosen=head;
            standard(suffix,cost,value,cap,chosen);
            for(int id:chosen) dst[id/64]|=uint64_t(1)<<(id%64);
        } else {
            if(mode==2 || !step || head!=last_head) {
                ++rebuild;
                state.reset(cap,words);
                for(int id:suffix) state.add(id,cost[id],value[id],true);
            } else {
                for(int id:batches[step]) state.add(id,cost[id],value[id],false);
            }
            peak=max(peak,static_cast<int>((state.values.size()+state.masks.size())*sizeof(int64_t)));
            memcpy(dst,&state.masks[static_cast<size_t>(cap)*words],sizeof(uint64_t)*words);
            for(int id:head) dst[id/64]|=uint64_t(1)<<(id%64);
            last_head=head;
        }
    }
    stats[0]=chrono::duration_cast<chrono::nanoseconds>(clock_type::now()-begin).count();
    stats[1]=rebuild;
    stats[2]=peak;
}

