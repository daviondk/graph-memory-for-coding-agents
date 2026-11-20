def empty_dit(list1):
    """
    Return True if all dictionaries in the input list are empty; otherwise False.
    Handle empty lists as True.
    """
    if not list1:
        return True
    for item in list1:
        if not isinstance(item, dict):
            return False
        if len(item) != 0:
            return False
    return True
