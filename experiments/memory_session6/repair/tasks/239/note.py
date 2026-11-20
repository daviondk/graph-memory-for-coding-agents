```python
def get_total_number_of_sequences(m, n):
    """
    Count sequences of length n where each element is >= 2x previous and <= m.
    
    A sequence is a list of integers a_1, a_2, ..., a_n such that:
    - 1 <= a_1 <= m
    - For i > 1: 2 * a_{i-1} <= a_i <= m
    
    Returns the total number of such sequences.
    """
    if n == 0:
        return 1
    if m < 1:
        return 0
    
    # dp[i][v] = number of sequences of length i ending with value v
    # We can optimize: for length 1, dp[1][v] = 1 for all v in 1..m
    # For length i > 1, dp[i][v] = sum of dp[i-1][u] for u in 1..floor(v/2)
    
    # Use a 1D array for the current length, and compute prefix sums for efficiency.
    
    # dp[v] for current length
    dp = [0] * (m + 1)
    for v in range(1, m + 1):
        dp[v] = 1
    
    for length in range(2, n + 1):
        new_dp = [0] * (m + 1)
        # Compute prefix sums of dp: prefix[v] = sum(dp[1..v])
        prefix = [0] * (m + 1)
        for v in range(1, m + 1):
            prefix[v] = prefix[v - 1] + dp[v]
        
        for v in range(1, m + 1):
            # new_dp[v] = sum of dp[u] for u in 1..floor(v/2
