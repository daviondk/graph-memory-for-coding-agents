#include <vector>
#include <cstdint>
#include <cmath>
// Exact 0/1 knapsack, preserve the earlier item on exact ties.
extern "C" __declspec(dllexport) void choose(int n, int cap, const int32_t* costs,
        const double* gains, uint8_t* selected) {
    std::vector<double> best(cap + 1, 0.0);
    std::vector<uint8_t> take(static_cast<size_t>(n) * (cap + 1), 0);
    for (int i=0; i<n; ++i) {
        for (int j=cap; j>=costs[i]; --j) {
            double alt = best[j-costs[i]] + gains[i];
            if (alt > best[j]) {
                best[j] = alt;
                take[static_cast<size_t>(i)*(cap+1)+j] = 1;
            }
        }
    }
    int j=cap;
    for (int i=n-1; i>=0; --i) {
        selected[i] = take[static_cast<size_t>(i)*(cap+1)+j];
        if (selected[i]) j-=costs[i];
    }
}
