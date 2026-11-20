def check_distinct(test_tup):
    """
    Check if all elements in the given tuple are distinct.
    
    Args:
        test_tup: A tuple of elements.
        
    Returns:
        True if all elements are distinct, False otherwise.
    """
    return len(test_tup) == len(set(test_tup))
