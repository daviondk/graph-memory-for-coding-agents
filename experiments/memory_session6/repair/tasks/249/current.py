def intersection_array(array_nums1, array_nums2):
    """
    Find the intersection of two arrays.
    
    Args:
        array_nums1: First list of numbers
        array_nums2: Second list of numbers
    
    Returns:
        A list containing the intersection of the two arrays (elements that appear in both),
        with duplicates preserved according to the minimum count in either array.
    """
    from collections import Counter
    
    count1 = Counter(array_nums1)
    count2 = Counter(array_nums2)
    
    result = []
    for num in count1:
        if num in count2:
            result.extend([num] * min(count1[num], count2[num]))
    
    return result
