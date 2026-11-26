#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <vector>

// tree columns: feature, threshold, global left index, global right index, leaf value.
extern "C" __declspec(dllexport) void tree_values(int n, int tree_count, const int32_t* roots,
        const double* nodes, double intercept, const double* x, double* out) {
    for (int i=0;i<n;++i) {
        double score=intercept;
        for (int k=0;k<tree_count;++k) {
            int at=roots[k];
            for (;;) {
                const double* node=nodes+at*5;
                int left=static_cast<int>(node[2]),right=static_cast<int>(node[3]);
                if (left==right) { score+=node[4];break; }
                at=x[i*8+static_cast<int>(node[0])]<=node[1] ? left:right;
            }
        }
        out[i]=score;
    }
}

// Output in original native order for every rule; it is part of the R39 contract.
extern "C" __declspec(dllexport) int pack(int n, int budget, int mode, const int32_t* order,
        const int32_t* costs, const double* gains, int32_t* out) {
    int written=0,left=budget,start=0;
    if (mode==0) {
        for (int j=0;j<n;++j) {
            int u=order[j];
            if (costs[u]<=left) {out[written++]=u;left-=costs[u];}
        }
        return written;
    }
    while(start<n && budget-left+costs[order[start]]<=budget/2) {
        int u=order[start++];
        out[written++]=u;left-=costs[u];
    }
    std::vector<int> tail;
    for(int j=start;j<n;++j) if(costs[order[j]]<=left) tail.push_back(order[j]);
    std::vector<uint8_t> chosen(tail.size(),0);
    if(mode==3) {
        int cap=left;
        std::vector<double> best(cap+1,0.);
        std::vector<uint8_t> take(tail.size()*(cap+1),0);
        for(size_t i=0;i<tail.size();++i) {
            int u=tail[i],cost=costs[u];
            for(int j=cap;j>=cost;--j) {
                double alt=best[j-cost]+gains[u];
                if(alt>best[j]) {best[j]=alt; take[i*(cap+1)+j]=1;}
            }
        }
        for(int i=static_cast<int>(tail.size())-1;i>=0;--i)
            if(take[i*(cap+1)+left]) {chosen[i]=1;left-=costs[tail[i]];}
    } else {
        std::vector<size_t> permutation(tail.size());
        std::iota(permutation.begin(),permutation.end(),0);
        std::vector<double> priority(tail.size());
        for(size_t i=0;i<tail.size();++i) priority[i]= mode==2 ? gains[tail[i]]/costs[tail[i]] : gains[tail[i]];
        std::stable_sort(permutation.begin(),permutation.end(),[&](size_t a,size_t b){return priority[a]>priority[b];});
        for(size_t i:permutation) if(costs[tail[i]]<=left) {chosen[i]=1;left-=costs[tail[i]];}
    }
    for(size_t i=0;i<tail.size();++i) if(chosen[i])out[written++]=tail[i];
    return written;
}
