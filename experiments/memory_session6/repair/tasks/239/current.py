```python
def get_total_number_of_sequences(m, n):
    """
    Count the number of sequences of length n where:
    - Each element is a positive integer
    - Each element is >= 2 * previous element
    - Each element is <= m
    """
    if n == 0:
        return 1
    if m <= 0:
        return 0
    
    # dp[i][j] = number of sequences of length i ending with value j
    # We can optimize: for a sequence of length i ending at value j,
    # the previous element must be in [1, j//2]
    
    # Base case: sequences of length 1 ending at value j (1 <= j <= m)
    # dp[1][j] = 1 for all j in 1..m
    
    # For length i > 1:
    # dp[i][j] = sum of dp[i-1][k] for k in 1..j//2
    
    # We can use prefix sums to compute this efficiently.
    
    # Let's use a 1D DP approach with prefix sums.
    # dp[j] for current length = sum of prev_dp[k] for k in 1..j//2
    
    # Initialize for length 1
    prev = [0] * (m + 1)
    for j in range(1, m + 1):
        prev[j] = 1
    
    if n == 1:
        return sum(prev[1:])
    
    for length in range(2, n + 1):
        curr = [0] * (m + 1)
        # Build prefix sum of prev
        prefix = [0] * (m + 1)
        for j in range(1, m + 1):
            prefix[j] = prefix[j - 1] + prev[j]
