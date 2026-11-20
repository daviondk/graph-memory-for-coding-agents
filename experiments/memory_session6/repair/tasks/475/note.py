from collections import Counter

def sort_counter(dict1):
    """
    Sort Counter items by value. Return sorted list of tuples.
    Handle ties consistently (by key in ascending order).
    Empty input returns empty list.
    """
    if not dict1:
        return []
    # Convert to list of (key, value) tuples
    items = list(dict1.items())
    # Sort by value (ascending), then by key (ascending) for consistent tie-breaking
    items.sort(key=lambda x: (x[1], x[0]))
    return items
