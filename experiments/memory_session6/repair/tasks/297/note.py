def flatten_list(list1):
    """
    Flatten a nested list recursively.
    
    Args:
        list1: A list that may contain nested lists and/or non-list elements.
        
    Returns:
        A flat list containing all elements from the nested structure.
    """
    result = []
    for item in list1:
        if isinstance(item, list):
            result.extend(flatten_list(item))
        else:
            result.append(item)
    return result
