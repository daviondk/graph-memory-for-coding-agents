def eulerian_num(n, m):
    """
    Compute the Eulerian number A(n, m), which counts the number of permutations
    of {1, 2, ..., n} with exactly m ascents.
    
    An ascent in a permutation p_1, p_2, ..., p_n is an index i (1 <= i < n)
    such that p_i < p_{i+1}.
    
    Parameters:
    n (int): The size of the permutation (n >= 0)
    m (int): The number of ascents (0 <= m <= n-1)
    
    Returns:
    int: The Eulerian number A(n, m)
    """
    if n < 0 or m < 0:
        return 0
    if n == 0:
        return 1 if m == 0 else 0
    if m >= n:
        return 0
    
    # Use dynamic programming
    # A(n, m) = (n - m) * A(n-1, m-1) + (m + 1) * A(n-1, m)
    # Base cases: A(0, 0) = 1, A(n, 0) = 1 for n >= 1
    
    # We'll build a table
    # dp[i][j] = A(i, j)
    dp = [[0] * (n + 1) for _ in range(n + 1)]
    dp[0][0] = 1
    
    for i in range(1, n + 1):
        for j in range(0, i):  # j ranges from 0 to i-1
            if j == 0:
                dp[i][j] = 1
            else:
                dp[i][j] = (i - j) * dp[i - 1][j - 1] + (j + 1) * dp[i - 1][j]
    
    return dp[n][m]
