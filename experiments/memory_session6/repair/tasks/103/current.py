def eulerian_num(n, m):
    """
    Compute the Eulerian number A(n, m), which counts the number of permutations
    of {1, 2, ..., n} with exactly m ascents.
    
    An ascent in a permutation is a position i (1 <= i < n) such that p[i] < p[i+1].
    
    The Eulerian numbers satisfy the recurrence:
    A(n, m) = (n - m) * A(n-1, m-1) + (m + 1) * A(n-1, m)
    
    with base cases:
    A(1, 0) = 1
    A(n, 0) = 1 for n >= 1
    A(n, m) = 0 if m < 0 or m >= n
    """
    if n < 1:
        return 0
    if m < 0 or m >= n:
        return 0
    if n == 1:
        return 1 if m == 0 else 0
    
    # Use dynamic programming
    # dp[i][j] = A(i, j)
    dp = [[0] * (n + 1) for _ in range(n + 1)]
    dp[1][0] = 1
    
    for i in range(2, n + 1):
        for j in range(0, i):
            dp[i][j] = (i - j) * dp[i - 1][j - 1] + (j + 1) * dp[i - 1][j]
    
    return dp[n][m]
