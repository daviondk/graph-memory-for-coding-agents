def get_total_number_of_sequences(m, n):
    """
    Find the number of possible sequences of length n such that each of the next element
    is greater than or equal to twice of the previous element but less than or equal to m.
    
    A sequence is a list of integers [a1, a2, ..., an] where:
    - 1 <= a1 <= m
    - For each i from 2 to n: 2 * a_{i-1} <= a_i <= m
    """
    if n == 0:
        return 1
    if m <= 0:
        return 0
    
    # dp[i][v] = number of sequences of length i ending with value v
    # We can optimize: for a given length i, the number of sequences ending with value v
    # is the sum of dp[i-1][u] for all u such that 2*u <= v, i.e., u <= v//2.
    
    # Let's use a 1D DP approach.
    # dp[v] = number of sequences of current length ending with value v
    # Initially (length 1): dp[v] = 1 for all v in 1..m
    
    # For length L from 2 to n:
    # new_dp[v] = sum of dp[u] for u in 1..v//2
    
    # We can precompute prefix sums to make this efficient.
    
    if n == 1:
        return m
    
    # dp[v] for v in 1..m, representing sequences of length 1
    dp = [0] * (m + 1)
    for v in range(1, m + 1):
        dp[v] = 1
    
    for length in range(2, n + 1):
        # Compute prefix sums of dp
        prefix = [0] * (m + 1)
        for v in range(1, m + 1):
            prefix[v] = prefix[v - 1] + dp[v]
        
        new_dp = [0] * (m + 1)
        for v in range(1, m + 1):
            # new_dp[v] = sum of dp[u] for u in 1..v//2
            max_u = v // 2
            if max_u >= 1:
                new_dp[v] = prefix[max_u]
            else:
                new_dp[v] = 0
        dp = new_dp
    
    return sum(dp[1:])
