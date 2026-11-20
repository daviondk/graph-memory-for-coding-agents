def overlapping(list1, list2):
    """
    Check whether any value in list1 exists in list2.
    
    Args:
        list1: First sequence to check.
        list2: Second sequence to check against.
    
    Returns:
        True if there is at least one common element, False otherwise.
    """
    return any(item in list2 for item in list1)
