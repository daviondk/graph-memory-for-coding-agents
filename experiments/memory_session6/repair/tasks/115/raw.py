def empty_dit(list1):
    """
    Check whether all dictionaries in a list are empty or not.
    
    Args:
        list1: A list of dictionaries.
        
    Returns:
        True if all dictionaries in the list are empty, False otherwise.
    """
    for item in list1:
        if not isinstance(item, dict):
            return False
        if len(item) != 0:
            return False
    return True
