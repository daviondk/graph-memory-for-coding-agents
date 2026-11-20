def get_max_triples(n):
    A = [i * i - i + 1 for i in range(1, n + 1)]
    count = [0, 0, 0]
    for x in A:
        count[x % 3] += 1
    ans = 0
    ans += count[0] * (count[0] - 1) * (count[0] - 2) // 6
    ans += count[1] * (count[1] - 1) * (count[1] - 2) // 6
    ans += count[2] * (count[2] - 1) * (count[2] - 2) // 6
    ans += count[0] * count[1] * count[2]
    return ans
