def sub_list(nums1, nums2):
    """
    Subtract corresponding elements from nums1 and nums2 using map and lambda.
    Handle length mismatches by truncating to the shorter list length.
    
    Args:
        nums1: First list of numbers
        nums2: Second list of numbers
    
    Returns:
        A list of differences (nums1[i] - nums2[i]) for i in range(min(len(nums1), len(nums2)))
    """
    min_len = min(len(nums1), len(nums2))
    return list(map(lambda x, y: x - y, nums1[:min_len], nums2[:min_len]))
