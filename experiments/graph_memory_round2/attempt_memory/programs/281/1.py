def all_unique(test_list):
    """
    Check if all elements in the given list are unique.
    
    Args:
        test_list: A list of elements.
        
    Returns:
        True if all elements are unique, False otherwise.
    """
    return len(test_list) == len(set(test_list))
