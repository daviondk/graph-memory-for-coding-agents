// Full joint optimization on integer scores. Only the protected suffix is passed in.
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <vector>
int main(){
    using I=std::int64_t;
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    int n,limit,pairs;
    if(!(std::cin>>n>>limit>>pairs)) return 1;
    std::vector<int> cost(n),mask(n),selection(n);
    std::vector<I> base(n),value(limit+1);
    std::vector<unsigned char> decisions(std::size_t(n)*(limit+1));
    for(int i=0;i<n;i++) std::cin>>cost[i]>>base[i];
    for(int pair=0;pair<pairs;pair++){
        int m;std::cin>>m;
        for(int i=0;i<n;i++)std::cin>>mask[i];
        for(int request=0;request<m;request++){
            I dx,dy;std::cin>>dx>>dy;
            std::fill(value.begin(),value.end(),0);
            for(int i=0;i<n;i++){
                I profit=base[i]+((mask[i]&1)?dx:0)+((mask[i]&2)?dy:0);
                auto row=decisions.data()+std::size_t(i)*(limit+1);
                for(int b=limit;b>=cost[i];b--){
                    I candidate=value[b-cost[i]]+profit;
                    row[b]=candidate>value[b];
                    if(row[b])value[b]=candidate;
                }
            }
            int b=limit;
            for(int i=n-1;i>=0;i--){
                selection[i]=cost[i]<=b && decisions[std::size_t(i)*(limit+1)+b];
                if(selection[i])b-=cost[i];
            }
            for(int i=0;i<n;i++)std::cout<<selection[i];
            std::cout<<'\n';
        }
    }
    return std::cin?0:2;
}
