def sort_counter(dict1):
    """
    Sort a dictionary by value.
    
    Args:
        dict1: A dictionary to sort by value.
        
    Returns:
        A list of tuples (key, value) sorted by value in ascending order.
    """
    return sorted(dict1.items(), key=lambda item: item[1])
