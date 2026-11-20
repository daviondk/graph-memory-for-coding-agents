def extract_rear(test_tuple):
    """
    Extract only the rear (last) index element of each string in the given tuple.
    
    Args:
        test_tuple: A tuple of strings.
        
    Returns:
        A tuple containing the last character of each string in the input tuple.
    """
    return tuple(s[-1] for s in test_tuple)
