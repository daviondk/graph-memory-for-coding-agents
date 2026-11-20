def count_element_in_list(list1, x):
    """
    Count sublists in list1 containing element x.
    
    Args:
        list1: A list of sublists (or elements).
        x: The element to search for in each sublist.
    
    Returns:
        Integer count of sublists that contain element x.
    """
    if not list1:
        return 0
    
    count = 0
    for sublist in list1:
        # Check if sublist is a list/tuple and contains x
        if isinstance(sublist, (list, tuple)):
            if x in sublist:
                count += 1
        else:
            # If sublist is not a list/tuple, check if it equals x
            if sublist == x:
                count += 1
    
    return count
