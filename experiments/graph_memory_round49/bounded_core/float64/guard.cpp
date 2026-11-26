// Use integer certificates to drop impossible choices; retain the native binary64 accumulation.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>
#include <vector>
#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif
using I=std::int64_t;
struct Item {int j,c;I v;double original;};
EXPORT int solve(int universe,int steps,int B,int T,int prune,const int* ends,const int* ids,const int* c,
                 const I* q,const double* v,int* selectedEnds,int* result,I* stats){
    int start=0, emitted=0;
    for(int s=0;s<steps;++s){
        int stop=ends[s],j=start,room=B;
        while(j<stop&&B-room+c[ids[j]]<=T){room-=c[ids[j]];result[emitted++]=ids[j++];}
        std::vector<Item> tail;I price=0,totalQ=0;
        for(;j<stop;++j)if(c[ids[j]]<=room){
            tail.push_back({j,c[ids[j]],q[j],v[j]});price+=c[ids[j]];totalQ+=q[j];
        }
        I* stat=stats+3*s;
        stat[0]=tail.size();stat[1]=0;stat[2]=0;
        if(price<=room){
            for(auto x:tail)result[emitted++]=ids[x.j];
        }else{
            if(prune){
                std::vector<int> order(tail.size());
                std::iota(order.begin(),order.end(),0);
                std::sort(order.begin(),order.end(),[&](int a,int b){
                    if(!tail[a].c||!tail[b].c)return tail[a].c!=tail[b].c?tail[a].c==0:a<b;
                    I lhs=tail[a].v*tail[b].c,rhs=tail[b].v*tail[a].c;
                    return lhs==rhs?a<b:lhs>rhs;
                });
                int left=room,split=-1;
                I cheap=0,ranked=0;
                for(int i:order){
                    const auto& x=tail[i];
                    if(x.c<=left){cheap+=x.v;left-=x.c;}else if(split<0)split=i;
                }
                left=room;
                for(const auto& x:tail)if(x.c<=left){ranked+=x.v;left-=x.c;}
                if(split<0)return -1;
                I num=tail[split].v, den=tail[split].c;
                I slack=num*room-std::max(cheap,ranked)*den;
                for(const auto& x:tail)slack+=std::max<I>(0,x.v*den-num*x.c);
                const I n=tail.size();
                // For positive binary64 utilities, a path has at most n additions.
                // Covers summation error on both paths and two half-Q32 errors per included item.
                I guard=n+4+I(std::ceil(4.L*n*std::numeric_limits<double>::epsilon()*(totalQ+n)));
                if(slack<0)return -2;
                stat[2]=guard;
                tail.erase(std::remove_if(tail.begin(),tail.end(),[&](const Item& x){
                    return num*x.c-x.v*den>slack+guard*den;
                }),tail.end());
                stat[1]=stat[0]-tail.size();
            }
            std::vector<double> best(room+1,0.0);
            std::vector<unsigned char> flags(tail.size()*(room+1),0);
            for(size_t i=0;i<tail.size();++i){
                const auto& x=tail[i];
                for(int b=room;b>=x.c;--b){
                    double alt=best[b-x.c]+x.original;
                    if(alt>best[b]){best[b]=alt;flags[i*(room+1)+b]=1;}
                }
            }
            int pos=room;std::vector<int> chosen;
            for(int i=int(tail.size())-1;i>=0;--i)if(flags[size_t(i)*(room+1)+pos]){
                chosen.push_back(ids[tail[i].j]);pos-=tail[i].c;
            }
            for(auto it=chosen.rbegin();it!=chosen.rend();++it)result[emitted++]=*it;
        }
        start=stop;selectedEnds[s]=emitted;
    }
    return emitted;
}
