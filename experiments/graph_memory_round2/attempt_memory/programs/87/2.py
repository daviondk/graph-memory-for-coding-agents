def merge_dictionaries_three(dict1, dict2, dict3):
    """
    Merge three dictionaries into one. Later keys override earlier ones.
    Handle empty inputs gracefully.
    """
    result = {}
    for d in (dict1, dict2, dict3):
        if d:
            result.update(d)
    return result
