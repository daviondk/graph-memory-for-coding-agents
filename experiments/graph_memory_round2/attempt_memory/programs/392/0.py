def get_max_sum(n):
    if n == 0:
        return 0
    if n < 2:
        return n
    memo = {}
    
    def helper(k):
        if k in memo:
            return memo[k]
        if k < 2:
            memo[k] = k
            return k
        a = helper(k // 2) + helper(k // 3) + helper(k // 4) + helper(k // 5)
        result = max(a, k)
        memo[k] = result
        return result
    
    return helper(n)
