def check_distinct(test_tup):
    """
    Check if the given tuple contains no duplicates.
    
    Args:
        test_tup: A tuple to check for duplicates.
        
    Returns:
        True if all elements are distinct, False otherwise.
    """
    return len(test_tup) == len(set(test_tup))
