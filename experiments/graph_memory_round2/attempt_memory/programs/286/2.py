def max_sub_array_sum_repeated(a, n, k):
    if k == 0:
        return 0
    if k == 1:
        return max_sub_array_sum(a, n)
    
    total = sum(a)
    if total <= 0:
        return max_sub_array_sum(a, n)
    
    # For k >= 2, the maximum subarray sum in the repeated array is:
    # max of:
    # 1. max subarray sum in single array
    # 2. total * (k - 2) + max subarray sum in two copies (a + a)
    # Actually, the standard result: if total > 0, the answer is total * (k - 2) + max subarray sum in a+a
    # But we need to be careful: the max subarray in the repeated array of length n*k
    # is max(max_subarray(a), total*(k-2) + max_subarray(a+a)) when k >= 2
    
    # Compute max subarray sum in a
    max_single = max_sub_array_sum(a, n)
    
    # Compute max subarray sum in a + a
    max_double = max_sub_array_sum(a + a, 2 * n)
    
    return max(max_single, total * (k - 2) + max_double)


def max_sub_array_sum(a, n):
    if n == 0:
        return 0
    max_ending_here = a[0]
    max_so_far = a[0]
    for i in range(1, n):
        max_ending_here = max(a[i], max_ending_here + a[i])
        max_so_far = max(max_so_far
