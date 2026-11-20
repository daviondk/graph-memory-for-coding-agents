def common_in_nested_lists(nestedlist):
    """
    Return list of elements present in all sublists.
    Handle empty inputs and non-list items.
    Preserve order of first occurrence.
    """
    if not nestedlist:
        return []
    
    # Filter out non-list items and empty sublists
    sublists = [item for item in nestedlist if isinstance(item, list)]
    
    if not sublists:
        return []
    
    # If any sublist is empty, no element can be common to all
    if any(len(sub) == 0 for sub in sublists):
        return []
    
    # Find common elements
    # Use the first sublist as the base, preserving its order
    base = sublists[0]
    common = []
    seen = set()
    
    for elem in base:
        if elem in seen:
            continue
        # Check if elem is in all other sublists
        if all(elem in sub for sub in sublists[1:]):
            common.append(elem)
            seen.add(elem)
    
    return common
