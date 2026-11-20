def trim_tuple(test_list, K):
    """
    Trim each tuple in the given list of tuples by K elements from the end.
    
    Args:
        test_list: A list of tuples.
        K: Number of elements to trim from the end of each tuple.
    
    Returns:
        A list of tuples, each trimmed by K elements from the end.
    """
    return [t[:-K] if K > 0 else t for t in test_list]
