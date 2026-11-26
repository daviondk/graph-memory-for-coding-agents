#include <algorithm>
#include <cstdint>
#include <limits>
#include <vector>

#ifdef _WIN32
#define PUBLIC extern "C" __declspec(dllexport)
#else
#define PUBLIC extern "C"
#endif

// Costs are strictly positive, values are nonnegative, and every total fits in int64.
PUBLIC void optimum(int count, int capacity, const int32_t* costs, const int64_t* values,
                    uint8_t* chosen, int64_t* frontier) {
    std::fill(frontier, frontier + capacity + 1, 0);
    std::fill(chosen, chosen + count, 0);
    std::vector<uint8_t> take(static_cast<size_t>(count) * (capacity + 1), 0);
    for (int i = 0; i < count; ++i) {
        for (int w = capacity; w >= costs[i]; --w) {
            const int64_t value = frontier[w-costs[i]] + values[i];
            if (value > frontier[w]) {
                frontier[w] = value;
                take[static_cast<size_t>(i) * (capacity + 1) + w] = 1;
            }
        }
    }
    for (int i = count-1, w = capacity; i >= 0; --i) {
        if (take[static_cast<size_t>(i) * (capacity + 1) + w]) {
            chosen[i] = 1;
            w -= costs[i];
        }
    }
}

// Highest feasible value among sets containing one or more newly available units.
PUBLIC int64_t competitor(int count, int capacity, const int32_t* costs,
                          const int64_t* values, const int64_t* old) {
    const auto impossible = std::numeric_limits<int64_t>::min();
    if (count == 1) {
        return costs[0] <= capacity ? old[capacity-costs[0]] + values[0] : impossible;
    }
    std::vector<int64_t> changed(capacity + 1, impossible);
    for (int i = 0; i < count; ++i) {
        for (int w = capacity; w >= costs[i]; --w) {
            const auto base = std::max(old[w-costs[i]], changed[w-costs[i]]);
            changed[w] = std::max(changed[w], base + values[i]);
        }
    }
    return changed[capacity];
}

