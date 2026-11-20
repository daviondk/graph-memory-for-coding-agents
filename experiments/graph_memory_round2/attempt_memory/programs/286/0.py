def max_sub_array_sum_repeated(a, n, k):
    if k == 0:
        return 0
    if k == 1:
        return max_subarray_sum(a, n)
    
    total_sum = sum(a)
    max_suffix = max_suffix_sum(a, n)
    max_prefix = max_prefix_sum(a, n)
    
    # Case 1: subarray entirely within one copy
    max_single = max_subarray_sum(a, n)
    
    # Case 2: subarray spans exactly two copies
    max_two = max_suffix + max_prefix
    
    # Case 3: subarray spans more than two copies (k >= 3)
    if k >= 3:
        max_multi = max_suffix + (k - 2) * total_sum + max_prefix
        return max(max_single, max_two, max_multi)
    else:
        return max(max_single, max_two)


def max_subarray_sum(a, n):
    if n == 0:
        return 0
    max_ending_here = a[0]
    max_so_far = a[0]
    for i in range(1, n):
        max_ending_here = max(a[i], max_ending_here + a[i])
        max_so_far = max(max_so_far, max_ending_here)
    return max_so_far


def max_suffix_sum(a, n):
    if n == 0:
        return 0
    max_suffix = a[n - 1]
    current = a[n - 1]
    for i in range(n - 2, -1, -1):
        current = max(a[i], current + a[i])
        max_suffix = max(max_suffix
