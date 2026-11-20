def merge_dictionaries_three(dict1, dict2, dict3):
    """
    Merge three dictionaries into a single dictionary.
    If there are duplicate keys, the value from the later dictionary takes precedence.
    """
    merged = {}
    merged.update(dict1)
    merged.update(dict2)
    merged.update(dict3)
    return merged
