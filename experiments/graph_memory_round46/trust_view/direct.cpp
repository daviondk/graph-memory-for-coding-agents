#include <algorithm>
#include <cstdint>
#include <vector>
#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif
// Per-thread scratch buffers avoid constructing a new decision table for each request.
EXPORT int select_ids(int n, int b, const int* c, const int64_t* u, const uint8_t* m,
                      int64_t delta, const uint16_t* prefix, int plen, const uint16_t* tail,
                      uint16_t* output) {
    static thread_local std::vector<int64_t> values;
    static thread_local std::vector<uint8_t> decision;
    values.assign(b+1,0);
    decision.resize(size_t(n)*(b+1));
    for(int i=0;i<n;++i) {
        int price=c[i];
        int64_t utility=u[i]+(m[i]?delta:0);
        auto* row=decision.data()+i*size_t(b+1);
        for(int w=b;w>=price;--w) {
            int64_t proposed=values[w-price]+utility;
            bool take=proposed>values[w];
            row[w]=take;
            if(take) values[w]=proposed;
        }
        // Entries below price are never queried during reconstruction.
    }
    for(int i=0;i<plen;++i) output[i]=prefix[i];
    int written=plen,remaining=b;
    for(int i=n-1;i>=0;--i) {
        if(c[i]<=remaining && decision[size_t(i)*(b+1)+remaining]) {
            output[written++]=tail[i];
            remaining-=c[i];
        }
    }
    std::reverse(output+plen,output+written);
    return written;
}
