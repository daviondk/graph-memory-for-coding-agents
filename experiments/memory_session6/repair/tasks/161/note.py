def remove_elements(list1, list2):
    """
    Remove elements from list1 that appear in list2.
    Return a new list with elements from list1 that are not in list2.
    Preserve order. Handle duplicates. Empty lists valid.
    """
    set2 = set(list2)
    return [item for item in list1 if item not in set2]
