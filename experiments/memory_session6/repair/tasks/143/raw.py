def find_lists(Input):
    """
    Find the number of lists present in the given tuple.
    
    Args:
        Input: A tuple that may contain lists and other elements.
        
    Returns:
        The count of lists in the tuple.
    """
    return sum(1 for item in Input if isinstance(item, list))
