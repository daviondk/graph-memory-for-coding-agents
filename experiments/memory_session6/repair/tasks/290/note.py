def max_length(list1):
    """
    Return list of sublists with max length.
    Handle empty input or ties by returning all matching sublists.
    Preserve original order.
    """
    if not list1:
        return []
    
    max_len = max(len(sub) for sub in list1)
    return [sub for sub in list1 if len(sub) == max_len]
