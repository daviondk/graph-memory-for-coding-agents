def common_in_nested_lists(nestedlist):
    """
    Find the common elements in given nested lists.
    
    Args:
        nestedlist: A list of lists (nested lists)
        
    Returns:
        A list of elements that are common to all sublists.
    """
    if not nestedlist:
        return []
    
    # Start with the first sublist's elements
    common = set(nestedlist[0])
    
    # Intersect with each subsequent sublist
    for sublist in nestedlist[1:]:
        common = common.intersection(set(sublist))
    
    return list(common)
