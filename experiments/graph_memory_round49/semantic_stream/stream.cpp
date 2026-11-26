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
            if(utility<=0)std::fill(flags,flags+stride,0);
            else for(int w=stride-1;w>=c;--w) {
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

// The dense-rank head changes membership as new rows arrive. Arbitrary optional rows may wake up.
API int serve(int n,int steps,int B,int T,int mode,int period,int cap,
              const int* births,const int* ids,const int* price,const I* base,
              const int* ownerOff,const int* owners,const int* deltaOff,const int* producer,const int* counts,
              int* ends,int* output,I* stats) {
    if(B<0||T<0||T>B||period<0||cap<0)return -1;
    std::vector<std::vector<int>> members;
    std::vector<int> support,rank;
    std::vector<I> raw(n),previous(n),optional(n);
    std::vector<U> fixed(n,0);
    auto allocate=[&](int a){
        if(a>=int(members.size())){members.resize(a+1);support.resize(a+1,0);}
    };
    Rows table;
    int visible=0,out=0;
    for(int step=1;step<=steps;++step){
        while(visible<n && births[visible]==step){
            const int i=visible++;
            raw[i]=base[i];
            for(int j=ownerOff[i];j<ownerOff[i+1];++j){
                const int a=owners[j];allocate(a);members[a].push_back(i);
                raw[i]+=I(std::min(cap,support[a]))*(I(1)<<28);
            }
            auto pos=std::lower_bound(rank.begin(),rank.end(),i,[&](int lhs,int rhs){return ids[lhs]<ids[rhs];});
            rank.insert(pos,i);
        }
        for(int j=deltaOff[step-1];j<deltaOff[step];++j){
            const int a=producer[j];allocate(a);
            const I shift=I(std::min(cap,counts[j])-std::min(cap,support[a]))*(I(1)<<28);
            support[a]=counts[j];
            if(shift)for(int i:members[a])raw[i]+=shift;
        }
        if(step==steps||(period>0&&step%period==0)){
            std::fill(fixed.begin(),fixed.begin()+visible,0);
            int used=0;
            for(int i:rank){
                if(used+price[i]>T)break;
                used+=price[i];fixed[i]=1;output[out++]=ids[i];
            }
            int dirty=visible;
            for(int i=0;i<visible;++i){
                optional[i]=fixed[i]?0:raw[i];
                if(optional[i]!=previous[i])dirty=std::min(dirty,i);
                previous[i]=optional[i];
            }
            int room=B-used;
            if(mode==0){
                std::vector<int> compact_prices, indices;
                std::vector<I> compact_values;
                for(int i=0;i<visible;++i)if(!fixed[i]){
                    compact_prices.push_back(price[i]);compact_values.push_back(raw[i]);indices.push_back(i);
                }
                table.solve(0,B,room,int(indices.size()),0,compact_prices.data(),compact_values);
                const int width=room+1;
                for(int k=int(indices.size())-1;k>=0;--k){
                    int i=indices[k];
                    if(price[i]<=room && table.decisions[size_t(k)*width+room]){
                        output[out++]=ids[i];room-=price[i];
                    }
                }
                ends[step-1]=out;
                continue;
            }
            table.solve(mode,B,room,visible,dirty,price,optional);
            const int width=(mode==0?room:B)+1;
            for(int i=visible-1;i>=0;--i){
                if(price[i]<=room && table.decisions[size_t(i)*width+room]){
                    output[out++]=ids[i];room-=price[i];
                }
            }
        }
        ends[step-1]=out;
    }
    stats[0]=table.visits;stats[1]=table.restored;stats[2]=table.peak;
    return visible==n?out:-3;
}
