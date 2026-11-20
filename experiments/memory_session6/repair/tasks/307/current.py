def colon_tuplex(tuplex, m, n):
    """
    Get a colon (slice) of a tuple.
    
    Parameters:
    tuplex: The input tuple
    m: Start index
    n: End index
    
    Returns:
    A tuple containing elements from index m to n-1
    """
    return tuple(tuplex[m:n])
