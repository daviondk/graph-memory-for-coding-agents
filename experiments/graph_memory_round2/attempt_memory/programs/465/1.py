def drop_empty(dict1):
    """
    Drop empty items from a given dictionary.
    
    An item is considered empty if its value is:
    - None
    - An empty string
    - An empty list
    - An empty tuple
    - An empty set
    - An empty frozenset
    - An empty dict
    - An empty bytes object
    - An empty bytearray
    - A boolean False (0)
    - The number 0 (int, float, complex)
    
    Returns a new dictionary with non-empty items.
    """
    result = {}
    for key, value in dict1.items():
        if _is_empty(value):
            continue
        result[key] = value
    return result


def _is_empty(value):
    """Check if a value is considered empty."""
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, set, frozenset, dict, bytes, bytearray)):
        return len(value) == 0
    if isinstance(value, (int, float, complex)):
        return value == 0
    if isinstance(value, bool):
        return value is False
    return False
