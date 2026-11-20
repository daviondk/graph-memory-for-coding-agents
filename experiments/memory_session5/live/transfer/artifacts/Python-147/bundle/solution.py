def get_max_triples(n):
    A = [i * i - i + 1 for i in range(1, n + 1)]
    counts = [0, 0, 0]
    for x in A:
        counts[x % 3] += 1
    c0, c1, c2 = counts
    ans = 0
    ans += c0 * (c0 - 1) * (c0 - 2) // 6
    ans += c1 * (c1 - 1) * (c1 - 2) // 6
    ans += c2 * (c2 - 1) * (c2 - 2) // 6
    ans += c0 * c1 * c2
    return ans
