def max_sum_increasing_subseq(a, n, index, k):
    """
    Find the maximum sum of an increasing subsequence from the prefix up to index `index`
    (inclusive), and also including the element at position `k` (where k > index).
    
    The subsequence must be strictly increasing in value.
    We consider elements from a[0..index] that form an increasing subsequence ending with
    some value less than a[k], and then append a[k].
    
    Returns the maximum sum of such a subsequence.
    """
    if index < 0 or k >= n or k <= index:
        return 0
    
    # We need to find the maximum sum of an increasing subsequence in a[0..index]
    # such that the last element is less than a[k], then add a[k].
    
    # Use DP: dp[i] = maximum sum of increasing subsequence ending at index i
    # where a[i] < a[k]
    
    # First, compute dp for all positions 0..index
    dp = [0] * (index + 1)
    for i in range(index + 1):
        dp[i] = a[i]
        for j in range(i):
            if a[j] < a[i]:
                if dp[j] + a[i] > dp[i]:
                    dp[i] = dp[j] + a[i]
    
    # Now find the maximum dp[i] where a[i] < a[k]
    max_prefix_sum = 0
    for i in range(index + 1):
        if a[i] < a[k]:
            if dp[i] > max_prefix_sum:
                max_prefix_sum = dp[i]
