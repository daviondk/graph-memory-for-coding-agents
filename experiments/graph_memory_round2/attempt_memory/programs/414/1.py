def overlapping(list1, list2):
    """
    Check whether any value in list1 exists in list2.
    
    Args:
        list1: A sequence (list, tuple, etc.) of elements.
        list2: A sequence (list, tuple, etc.) of elements.
    
    Returns:
        True if there is at least one common element between list1 and list2,
        False otherwise.
    """
    # Convert to sets for efficient lookup, handling edge cases like empty sequences
    set2 = set(list2)
    for item in list1:
        if item in set2:
            return True
    return False
