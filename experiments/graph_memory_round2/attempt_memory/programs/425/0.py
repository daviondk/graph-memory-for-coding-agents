def count_element_in_list(list1, x):
    """
    Count the number of sublists in list1 that contain the element x.
    
    Args:
        list1: A list of sublists (each sublist is a list).
        x: The element to search for in each sublist.
    
    Returns:
        The number of sublists that contain x.
    """
    count = 0
    for sublist in list1:
        if x in sublist:
            count += 1
    return count
