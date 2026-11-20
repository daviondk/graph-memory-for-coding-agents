def is_sublist(l, s):
    """
    Check whether list l contains the given sublist s.
    
    Args:
        l: The list to search in.
        s: The sublist to look for.
    
    Returns:
        True if s is a contiguous sublist of l, False otherwise.
    """
    if not s:
        return True
    n = len(l)
    m = len(s)
    if m > n:
        return False
    for i in range(n - m + 1):
        if l[i:i + m] == s:
            return True
    return False
