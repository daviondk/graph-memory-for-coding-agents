def sort_sublists(input_list):
    """
    Sort each sublist of strings in a given list of lists.
    
    Args:
        input_list: A list of lists of strings.
        
    Returns:
        A new list where each sublist is sorted in ascending order.
    """
    return [sorted(sublist) for sublist in input_list]
