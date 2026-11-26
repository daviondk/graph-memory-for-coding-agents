#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

// Maximize utility at one specified, feasible token cost. Strict > preserves the earlier unit on ties.
extern "C" __declspec(dllexport) int choose_exact(int n, int cap, const int32_t* costs,
        const double* gains, uint8_t* selected) {
    std::vector<double> value(cap+1, -std::numeric_limits<double>::infinity());
    std::vector<uint8_t> used(static_cast<size_t>(n)*(cap+1),0);
    value[0]=0;
    for (int i=0; i<n; ++i) {
        for (int j=cap; j>=costs[i]; --j) {
            const double candidate=value[j-costs[i]] + gains[i];
            if (candidate>value[j]) {
                value[j]=candidate;
                used[static_cast<size_t>(i)*(cap+1)+j]=1;
            }
        }
    }
    if (!std::isfinite(value[cap])) return 0;
    int remaining=cap;
    for (int i=n-1; i>=0; --i) {
        selected[i]=used[static_cast<size_t>(i)*(cap+1)+remaining];
        if (selected[i]) remaining-=costs[i];
    }
    return remaining==0;
}
