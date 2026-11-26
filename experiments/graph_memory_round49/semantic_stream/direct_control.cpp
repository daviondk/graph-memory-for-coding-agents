// Optimized direct Dense-FT first-fit and an unchanged exact semantic-head comparison.
// The caller supplies native dense rank as the stable ID.
#define serve exact_stream
#include "stream.cpp"
#undef serve

API int serve(int n,int steps,int B,int T,int mode,int period,int cap,
              const int* births,const int* ids,const int* price,const I* base,
              const int* ownerOff,const int* owners,const int* deltaOff,const int* producer,const int* counts,
              int* ends,int* output,I* stats) {
    if(mode!=101)return exact_stream(n,steps,B,T,mode,period,cap,births,ids,price,base,ownerOff,owners,
                                 deltaOff,producer,counts,ends,output,stats);
    std::vector<int> rank;
    rank.reserve(n);
    int visible=0,out=0;
    I inspected=0;
    for(int t=1;t<=steps;++t){
        while(visible<n&&births[visible]==t){
            int i=visible++;
            auto pos=std::lower_bound(rank.begin(),rank.end(),i,[&](int a,int b){return ids[a]<ids[b];});
            rank.insert(pos,i);
        }
        int room=B;
        for(int i:rank){
            ++inspected;
            if(price[i]<=room){output[out++]=ids[i];room-=price[i];}
        }
        ends[t-1]=out;
    }
    stats[0]=inspected;stats[1]=0;stats[2]=rank.capacity()*sizeof(int);
    return out;
}
