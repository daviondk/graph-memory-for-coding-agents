def trim_tuple(test_list, K):
    """
    Trim each tuple in the list by K elements.
    
    Args:
        test_list: A list of tuples.
        K: Number of elements to trim from each tuple.
        
    Returns:
        A new list with each tuple trimmed by K elements.
        If K is 0, returns the original tuples unchanged.
        If K exceeds the tuple length, returns an empty tuple.
    """
    if K <= 0:
        return [t for t in test_list]
    
    result = []
    for t in test_list:
        if K >= len(t):
            result.append(())
        else:
            result.append(t[:len(t) - K])
    return result
