def max_sum_increasing_subseq(a, n, index, k):
    """
    Find the maximum sum of an increasing subsequence from prefix until index i,
    including the kth element (k > i).
    
    The subsequence must be strictly increasing, start somewhere in a[0..index],
    end at a[k], and include a[k].
    """
    if index >= k:
        return -1  # invalid, k must be > index
    
    # We need to find the max sum of an increasing subsequence in a[0..index]
    # such that the last element is less than a[k], then add a[k].
    
    # Let dp[j] = max sum of increasing subsequence ending at j (j in 0..index)
    # We want max over j where a[j] < a[k] of dp[j] + a[k]
    # Also, the subsequence could be just a[k] itself (sum = a[k])
    
    # Compute dp for indices 0..index
    dp = [0] * n
    for i in range(n):
        dp[i] = a[i]
        for j in range(i):
            if a[j] < a[i] and dp[j] + a[i] > dp[i]:
                dp[i] = dp[j] + a[i]
    
    # Now find max dp[j] for j in 0..index where a[j] < a[k]
    best = -1
    for j in range(index + 1):
        if a[j] < a[k]:
            if dp[j] > best:
                best = dp[j]
    
    if best == -1:
        return a[k]  #
