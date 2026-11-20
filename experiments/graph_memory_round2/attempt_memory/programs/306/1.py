def max_sum_increasing_subseq(a, n, index, k):
    """
    Find the maximum sum of an increasing subsequence from prefix until index (inclusive)
    and also including the kth element (a[k]), where k > index.
    
    The subsequence must be strictly increasing, start from a[0..index], include a[k],
    and all elements before a[k] must be < a[k].
    
    Args:
        a: list of numbers
        n: length of the list
        index: the last index in the prefix (0-based)
        k: the index of the element that must be included (0-based), k > index
    
    Returns:
        Maximum sum of such subsequence, or 0 if no valid subsequence exists.
    """
    if k <= index:
        return 0
    if index < 0 or k >= n or index >= n:
        return 0
    
    # dp[i] = maximum sum of increasing subsequence ending at index i, using only elements from 0..i
    dp = [0] * (index + 1)
    for i in range(index + 1):
        dp[i] = a[i]
        for j in range(i):
            if a[j] < a[i]:
                dp[i] = max(dp[i], dp[j] + a[i])
    
    # Now we need to include a[k]. All elements in the subsequence before a[k] must be < a[k].
    # So we look for the best dp[i] where a[i] < a[k], and add a[k] to it.
    # Also, the subsequence could just be [a[k]] itself, so consider a[k] alone.
