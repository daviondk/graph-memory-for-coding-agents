def check_element(lst, element):
    """
    Check whether all items of a list are equal to a given string.
    
    Args:
        lst: A list of elements.
        element: A string to compare against.
    
    Returns:
        True if all items in the list are equal to the given string, False otherwise.
    """
    return all(item == element for item in lst)
