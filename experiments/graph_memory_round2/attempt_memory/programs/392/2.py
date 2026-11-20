def get_max_sum(n):
    memo = {}
    
    def helper(x):
        if x < 1:
            return 0
        if x in memo:
            return memo[x]
        result = max(helper(x // 2) + helper(x // 3) + helper(x // 4) + helper(x // 5), x)
        memo[x] = result
        return result
    
    return helper(n)
