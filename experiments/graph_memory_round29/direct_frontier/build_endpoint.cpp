#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace {
constexpr int cap = 384;
constexpr int levels = 10;
constexpr float none = -std::numeric_limits<float>::infinity();

void enumerate(const float* a, const float* b, const std::int16_t* seg, int n, int k, int* left, int* right) {
    std::array<float,cap> best_end, best_start;
    best_end.fill(none); best_start.fill(none);
    for (int i=0;i<n;++i) {
        if (seg[i]<0) continue;
        for (int j=i;j<std::min(n,i+k);++j) {
            if (seg[i]!=seg[j]) continue;
            float s=a[i]+b[j];
            if (s>best_end[j]) { best_end[j]=s; left[j]=i; }
            if (s>best_start[i]) { best_start[i]=s; right[i]=j; }
        }
    }
}

struct SparseMax {
    std::array<std::array<float, cap>, levels> tab;
    int count=1;
    SparseMax(const float* data, int n, int k) {
        std::copy(data,data+n,tab[0].begin());
        for (int s=2;s<=std::min(n,k);s*=2,++count) {
            for (int i=0;i+s<=n;++i) tab[count][i]=std::max(tab[count-1][i],tab[count-1][i+s/2]);
        }
    }
    int earliest(int l,int r,float offset) const {
        const int z=31-__builtin_clz(static_cast<unsigned>(r-l+1));
        float score=std::max(tab[z][l],tab[z][r-(1<<z)+1])+offset;
        for (int level=z;level>=0;--level) {
            int step=1<<level;
            if (l+step-1<=r && tab[level][l]+offset<score) l+=step;
        }
        return l;
    }
};

void maxima(const float* a, const float* b, int lo,int hi,int k,int* left,int* right) {
    auto starts=SparseMax(a+lo,hi-lo,k);
    auto ends=SparseMax(b+lo,hi-lo,k);
    for (int i=lo;i<hi;++i) {
        left[i]=lo+starts.earliest(std::max(0,i-lo-k+1),i-lo,b[i]);
        right[i]=lo+ends.earliest(i-lo,std::min(hi-lo-1,i-lo+k-1),a[i]);
    }
}

void deque_pass(const float* v,const float* offs,int lo,int hi,int k,bool reverse,int* out) {
    std::array<int,cap> deq; int first=0,last=0;
    for (int step=0;step<hi-lo;++step) {
        int p=reverse?hi-1-step:lo+step;
        int l=reverse?p:std::max(lo,p-k+1), r=reverse?std::min(hi-1,p+k-1):p;
        while(first<last && (deq[first]<l || deq[first]>r)) ++first;
        // Reverse scan encounters earlier indices later, so equal new maxima dominate.
        while(first<last && (reverse?v[deq[last-1]]<=v[p]:v[deq[last-1]]<v[p])) --last;
        deq[last++]=p;
        int best=deq[first]; float s=v[best]+offs[p];
        // If even the representable predecessor loses, no strictly smaller logit can tie the rounded sum.
        if (best>l && std::nextafter(v[best],none)+offs[p]==s)
            for (int j=l;j<best;++j) if (v[j]+offs[p]==s) {best=j;break;}
        out[p]=best;
    }
}

bool contiguous(const std::int16_t* seg,int n) {
    int previous=-1;
    for (int i=0;i<n;++i) {
        if (seg[i]<0 || (i && seg[i]==seg[i-1])) continue;
        if (seg[i]<=previous) return false;
        previous=seg[i];
    }
    return true;
}
}

extern "C" __declspec(dllexport)
int endpoints(int method,const float* a,const float* b,const std::int16_t* seg,int n,int k,int* left,int* right) {
    if(n<0 || n>cap || k<1) return -1;
    std::fill(left,left+n,-1);std::fill(right,right+n,-1);
    if (method==0 || !contiguous(seg,n)) { enumerate(a,b,seg,n,k,left,right);return 0; }
    for(int i=0;i<n;) {
        int j=i+1;while(j<n && seg[j]==seg[i])++j;
        if(seg[i]>=0) {
            if(method==1) maxima(a,b,i,j,k,left,right);
            else {
                deque_pass(a,b,i,j,k,false,left);
                deque_pass(b,a,i,j,k,true,right);
            }
        }
        i=j;
    }
    return method;
}
