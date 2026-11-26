// Exact Q32 knapsack with fractional upper bounds and optional previous-packet lower bounds.
#include <algorithm>
#include <cstdint>
#include <numeric>
#include <vector>
#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif
using I=std::int64_t;
struct Item {int rank,id,c; I v;};

static void exact(const std::vector<Item>& items,int room,std::vector<unsigned char>& take,I* cells) {
    std::vector<I> value(room+1,0);
    std::vector<unsigned char> bits(items.size()*(room+1),0);
    for(size_t j=0;j<items.size();++j){
        const auto& x=items[j];
        if(x.c>room)continue;
        *cells+=room-x.c+1;
        for(int w=room;w>=x.c;--w){
            I alt=value[w-x.c]+x.v;
            if(alt>value[w]){
                value[w]=alt;
                bits[j*(room+1)+w]=1;
            }
        }
    }
    int w=room;
    for(int j=int(items.size())-1;j>=0;--j)if(bits[size_t(j)*(room+1)+w]){
        take[items[j].rank]=1; w-=items[j].c;
    }
}

// Stats per snapshot: tail, forced, rejected, unresolved, visited DP cells, improved LB, extra Q32, fits.
EXPORT int choose(int universe,int steps,int B,int T,int mode,const int* ends,const int* ids,
                  const int* costs,const I* values,int* outEnds,int* output,I* stats) {
    std::vector<unsigned char> prior(universe,0);
    int off=0, out=0;
    for(int s=0;s<steps;++s){
        I* counter=stats+8*s;std::fill(counter,counter+8,0);
        const int size=ends[s]-off;int first=0, used=0;I tailcost=0;
        std::vector<unsigned char> chosen(size,0);
        while(first<size && used+costs[ids[off+first]]<=T){
            used+=costs[ids[off+first]];chosen[first++]=1;
        }
        int room=B-used;
        std::vector<Item> rows;
        for(int rank=first;rank<size;++rank){
            int id=ids[off+rank],c=costs[id];
            I v=values[off+rank];
            if(c<0||v<0)return -1;
            if(c<=room){rows.push_back({rank,id,c,v});tailcost+=c;}
        }
        counter[0]=rows.size();
        if(tailcost<=room){
            counter[7]=1;
            for(const auto& x:rows)if(x.v>0)chosen[x.rank]=1;
        }else if(mode==0){
            counter[3]=rows.size();
            exact(rows,room,chosen,counter+4);
        }else{
            // Nonpositive utility can be dropped under the original rank-tie rule.
            std::vector<Item> cand;
            for(const auto& x:rows){
                if(x.v==0){++counter[2];continue;}
                if(x.c==0){chosen[x.rank]=1;++counter[1];continue;}
                cand.push_back(x);
            }
            std::vector<int> order(cand.size());
            std::iota(order.begin(),order.end(),0);
            std::sort(order.begin(),order.end(),[&](int a,int b){
                I l=cand[a].v*cand[b].c,r=cand[b].v*cand[a].c;
                return l==r ? a<b : l>r;
            });
            int available=room,split=-1;
            I greedy=0;
            for(int j:order){
                auto& x=cand[j];
                if(x.c<=available){available-=x.c;greedy+=x.v;}
                else if(split<0)split=j;
            }
            if(split<0){for(const auto& x:cand)chosen[x.rank]=1;counter[1]+=cand.size();}
            else{
                I lower=greedy;
                if(mode>=2){
                    std::vector<unsigned char> selected(cand.size(),0);
                    int left=room;I warm=0;
                    for(size_t j=0;j<cand.size();++j){
                        auto& x=cand[j];
                        if((mode==3||prior[x.id]) && x.c<=left){left-=x.c;warm+=x.v;selected[j]=1;}
                    }
                    for(int j:order)if(!selected[j]&&cand[j].c<=left){left-=cand[j].c;warm+=cand[j].v;}
                    if(warm>lower){counter[5]=1;counter[6]=warm-lower;lower=warm;}
                }
                const I num=cand[split].v,den=cand[split].c;
                I slack=num*room-lower*den;
                for(auto& x:cand)slack+=std::max<I>(0,x.v*den-num*x.c);
                if(slack<0)return -2;
                std::vector<Item> core;
                for(auto& x:cand){
                    I reduced=x.v*den-num*x.c;
                    if(reduced>slack){chosen[x.rank]=1;room-=x.c;++counter[1];}
                    else if(-reduced>slack){++counter[2];}
                    else core.push_back(x);
                }
                if(room<0)return -3;
                counter[3]=core.size();exact(core,room,chosen,counter+4);
            }
        }
        std::fill(prior.begin(),prior.end(),0);
        for(int j=0;j<size;++j)if(chosen[j]){
            int id=ids[off+j];prior[id]=1;output[out++]=id;
        }
        outEnds[s]=out;off=ends[s];
    }
    return out;
}
