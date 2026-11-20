def max_length(list1):
    """
    Find the list of maximum length in a list of lists.
    
    Args:
        list1: A list of lists.
        
    Returns:
        The list with the maximum length. If there are multiple lists with the same maximum length,
        returns the first one encountered. If the input list is empty, returns an empty list.
    """
    if not list1:
        return []
    
    max_list = list1[0]
    for lst in list1[1:]:
        if len(lst) > len(max_list):
            max_list = lst
    return max_list
