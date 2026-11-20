def max_length(list1):
    """
    Find the list of lists with maximum length.
    
    Args:
        list1: A list of lists.
        
    Returns:
        The list (or lists) with the maximum length.
    """
    if not list1:
        return []
    
    max_len = max(len(sublist) for sublist in list1)
    return [sublist for sublist in list1 if len(sublist) == max_len]
