from collections import Counter

def extract_freq(test_list):
    """
    Return a dict mapping unique tuples to counts.
    Order-insensitive: elements within each tuple are sorted before counting.
    Handles empty list.
    """
    if not test_list:
        return {}
    
    # Convert each element to a sorted tuple (order-insensitive)
    normalized = [tuple(sorted(item)) for item in test_list]
    
    # Count occurrences
    counts = Counter(normalized)
    
    return dict(counts)
