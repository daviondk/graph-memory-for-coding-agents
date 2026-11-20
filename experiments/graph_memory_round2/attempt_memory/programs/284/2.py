def check_element(lst, element):
    """
    Return True if every item in lst equals the given string `element`; otherwise False.
    Empty lists are considered True.
    """
    for item in lst:
        if item != element:
            return False
    return True
