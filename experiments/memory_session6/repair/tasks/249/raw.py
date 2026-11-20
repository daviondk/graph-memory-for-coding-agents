def intersection_array(array_nums1, array_nums2):
    """
    Find the intersection of two arrays using a lambda function.
    
    Args:
        array_nums1: First list of numbers
        array_nums2: Second list of numbers
    
    Returns:
        A list containing the intersection of the two arrays (elements common to both)
    """
    # Use a lambda to filter elements from array_nums1 that are also in array_nums2
    intersection = list(filter(lambda x: x in array_nums2, array_nums1))
    return intersection
