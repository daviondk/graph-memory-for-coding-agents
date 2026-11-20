def flatten_list(list1):
    """
    Flatten a nested list structure into a single-level list.
    
    Args:
        list1: A potentially nested list.
        
    Returns:
        A flattened list containing all non-list elements.
    """
    result = []
    for item in list1:
        if isinstance(item, list):
            result.extend(flatten_list(item))
        else:
            result.append(item)
    return result
