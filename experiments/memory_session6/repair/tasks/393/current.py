def max_length_list(input_list):
    """
    Find the list with maximum length from a list of lists.
    
    Args:
        input_list: A list containing sublists.
        
    Returns:
        The sublist with the maximum length. If there are multiple sublists
        with the same maximum length, returns the first one encountered.
        If the input list is empty, returns an empty list.
    """
    if not input_list:
        return []
    
    return max(input_list, key=len)
