// Rows outside the residual feasible set never reach either forest.
#include <cstdint>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif

API int undecided(int n, const int* rank, const int* costs, int* indices) {
    int j=0, room=2048, num=0, total=0;
    while (j<n && 2048-room+costs[rank[j]]<=1024) room-=costs[rank[j++]];
    for (int i=j; i<n; ++i) {
        int id=rank[i];
        if (costs[id]<=room) {indices[num++]=id; total+=costs[id];}
    }
    return total<=room ? 0 : num;
}

API void evaluate(int count, const int* indices, int specialize, int trees,
                  const int* roots, const double* nodes, double bias,
                  const double* matrix, double* out) {
    for (int j=0; j<count; ++j) {
        int i=indices ? indices[j] : j;
        const double* x=matrix+8*i;
        if (specialize) { out[i]=compiled(x); continue; }
        double v=bias;
        for (int k=0; k<trees; ++k) {
            int at=roots[k];
            while (true) {
                const double* node=nodes+5*at;
                int left=static_cast<int>(node[2]), right=static_cast<int>(node[3]);
                if (left==right) { v+=node[4]; break; }
                at=x[static_cast<int>(node[0])]<=node[1] ? left : right;
            }
        }
        out[i]=v;
    }
}

