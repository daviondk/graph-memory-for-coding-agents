def eulerian_num(n, m):
    """
    Compute the Eulerian number A(n, m).
    
    The Eulerian number A(n, m) counts the number of permutations of {1, 2, ..., n}
    with exactly m ascents.
    
    Parameters:
    n (int): Non-negative integer
    m (int): Non-negative integer
    
    Returns:
    int: The Eulerian number A(n, m), or 0 if m > n-1 or m < 0
    """
    if n < 0 or m < 0:
        return 0
    if n == 0:
        return 1 if m == 0 else 0
    if m > n - 1:
        return 0
    
    # Use the recurrence relation:
    # A(n, m) = (n - m) * A(n-1, m) + (m + 1) * A(n-1, m-1)
    # Base cases: A(0, 0) = 1, A(n, 0) = 1 for n >= 1
    
    # Build up using dynamic programming
    # dp[m] represents A(current_n, m)
    dp = [0] * (n)  # m ranges from 0 to n-1
    
    # Base case: n = 1, A(1, 0) = 1
    dp[0] = 1
    
    for i in range(2, n + 1):
        # Update dp in reverse order to avoid overwriting values we still need
        # m ranges from 0 to i-1
        new_dp = [0] * i
        for j in range(i):
            if j == 0:
                new_dp[j] = 1  # A(i, 0) = 1
            else:
                # A(i, j) = (i - j) * A(i-1, j) + (j + 1) * A(i-1, j-1)
                term1 = (i - j) * dp[j] if j < len(dp) else 0
                term2 = (j + 1) * dp[j - 1]
                new_dp[j] = term1 + term2
        dp = new_dp
    
    return dp[m]
