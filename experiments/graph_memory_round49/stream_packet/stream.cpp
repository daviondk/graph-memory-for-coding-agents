// Exact budgeted view over arriving items and signed revisions of producer support.
#include <algorithm>
#include <cstdint>
#include <limits>
#include <vector>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif
using I = int64_t;
using U = uint8_t;

struct Rows {
    std::vector<I> best, checkpoints;
    std::vector<U> decisions;
    int done=0;
    I visits=0, restored=0, peak=0;
    void solve(int mode,int budget,int room,int cut,int dirty,const int* price,const std::vector<I>& values) {
        const int stride=(mode==0?room:budget)+1;
        int begin=0;
        if(mode==0) best.assign(stride,0);
        else {
            if(best.empty())best.assign(stride,0);
            if(dirty>=done)begin=done;
            else if(mode>0) {
                begin=(dirty/mode)*mode;
                if(begin)std::copy_n(checkpoints.data()+size_t(begin/mode-1)*stride,stride,best.data());
                else std::fill(best.begin(),best.end(),0);
                restored+=done-begin;
            } else {
                std::fill(best.begin(),best.end(),0);
                restored+=done;
            }
        }
        if(cut<begin)return;
        decisions.resize(size_t(cut)*stride);
        if(mode>0)checkpoints.resize(size_t(cut/mode)*stride);
        for(int i=begin;i<cut;++i) {
            int c=price[i]; I utility=values[i];
            U* flags=decisions.data()+size_t(i)*stride;
            for(int w=stride-1;w>=c;--w) {
                I candidate=best[w-c]+utility;
                flags[w]=(candidate>best[w]);
                if(flags[w])best[w]=candidate;
            }
            if(mode>0&&(i+1)%mode==0) {
                auto* dest=checkpoints.data()+size_t((i+1)/mode-1)*stride;
                std::copy(best.begin(),best.end(),dest);
            }
        }
        done=cut;visits+=cut-begin;
        peak=std::max(peak,I((best.capacity()+checkpoints.capacity())*sizeof(I)+decisions.capacity()*sizeof(U)));
    }
};

// Returned packet IDs are ordered newest first. Mode 0 is from-scratch and -1 saves no checkpoints.
API int serve(int n,int steps,int B,int T,int mode,int period,int cap,
              const int* births,const int* ids,const int* price,const I* base,
              const int* ownerOff,const int* owners,const int* deltaOff,const int* producer,const int* counts,
              int* ends,int* output,I* stats) {
    if(B<0||T<0||T>B||period<0||cap<0)return -1;
    std::vector<std::vector<int>> members;
    std::vector<int> support;
    std::vector<I> cumulative(1,0),values;
    auto make_source=[&](int id) {
        if(id>=int(support.size())){support.resize(id+1,0);members.resize(id+1);}
    };
    Rows rows;int out=0,dirty=n,visible=0;
    for(int step=1;step<=steps;++step) {
        while(visible<n&&births[visible]==step) {
            int i=visible++;I v=base[i];
            for(int j=ownerOff[i];j<ownerOff[i+1];++j) {
                const int a=owners[j];make_source(a);
                members[a].push_back(i);v+=I(std::min(cap,support[a]))*(I(1)<<28);
            }
            values.push_back(v);cumulative.push_back(cumulative.back()+price[i]);
        }
        for(int j=deltaOff[step-1];j<deltaOff[step];++j) {
            int a=producer[j];make_source(a);
            I shift=I(std::min(cap,counts[j])-std::min(cap,support[a]))*(I(1)<<28);
            support[a]=counts[j];
            if(!shift) continue;
            for(int i:members[a]){values[i]+=shift;dirty=std::min(dirty,i);}
        }
        if(step==steps||(period>0&&step%period==0)) {
            const I bound=cumulative.back()-T;
            const int cut=int(std::lower_bound(cumulative.begin(),cumulative.end(),bound)-cumulative.begin());
            int room=B-int(cumulative.back()-cumulative[cut]);
            if(rows.done>cut)return -2;
            rows.solve(mode,B,room,cut,dirty,price,values);
            int width=(mode==0?room:B)+1;
            for(int i=visible-1;i>=cut;--i)output[out++]=ids[i];
            for(int i=cut-1;i>=0;--i) {
                if(price[i]<=room&&rows.decisions[size_t(i)*width+room]) {
                    output[out++]=ids[i];room-=price[i];
                }
            }
            dirty=n;
        }
        ends[step-1]=out;
    }
    stats[0]=rows.visits;stats[1]=rows.restored;stats[2]=rows.peak;
    return visible==n?out:-3;
}
