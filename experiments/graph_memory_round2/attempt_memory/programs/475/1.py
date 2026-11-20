from collections import Counter


def sort_counter(dict1):
    """
    Sort a Counter (or dict) by value in descending order.
    
    Args:
        dict1: A Counter object or dictionary to sort by value.
        
    Returns:
        A list of (key, value) tuples sorted by value in descending order.
    """
    return sorted(dict1.items(), key=lambda item: item[1], reverse=True)
