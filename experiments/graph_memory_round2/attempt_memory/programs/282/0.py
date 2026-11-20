def sub_list(nums1, nums2):
    """
    Subtract two lists element-wise.
    
    Args:
        nums1: First list of numbers
        nums2: Second list of numbers
    
    Returns:
        A new list where each element is nums1[i] - nums2[i]
    """
    return [a - b for a, b in zip(nums1, nums2)]
