def get_max_sum(n):
    if n < 2:
        return n
    memo = {}
    def f(x):
        if x < 2:
            return x
        if x in memo:
            return memo[x]
        total = f(x // 2) + f(x // 3) + f(x // 4) + f(x // 5)
        result = max(total, x)
        memo[x] = result
        return result
    return f(n)
