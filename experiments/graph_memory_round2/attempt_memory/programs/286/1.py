def max_sub_array_sum_repeated(a, n, k):
    """
    Find the largest sum of a contiguous subarray in the array formed by repeating 'a' k times.
    
    Args:
        a: list of integers (the original array)
        n: length of the array
        k: number of times to repeat the array
    
    Returns:
        Maximum sum of a contiguous subarray in the repeated array
    """
    if k == 0 or n == 0:
        return 0
    
    total_sum = sum(a)
    
    # If k == 1, just find max subarray sum of a
    if k == 1:
        return _max_subarray_sum(a)
    
    # For k >= 2, the max subarray can be:
    # 1. Entirely within one copy (max subarray of a)
    # 2. Spanning multiple copies (involves suffix of one + full copies + prefix of another)
    
    # Compute max subarray sum of a
    max_single = _max_subarray_sum(a)
    
    # Compute max suffix sum of a
    max_suffix = _max_suffix_sum(a)
    
    # Compute max prefix sum of a
    max_prefix = _max_prefix_sum(a)
    
    # Case 1: subarray within one copy
    # Case 2: subarray spanning at least 2 copies
    # If total_sum > 0, then including more full copies increases the sum
    # The best spanning subarray would be: max_suffix + (k-2) * total_sum + max_prefix (for k >= 2)
    # But we need to be careful: the spanning subarray can span from suffix of copy i
