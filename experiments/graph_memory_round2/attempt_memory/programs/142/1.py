def count_samepair(list1, list2, list3):
    """
    Count the number of positions where all three lists have identical items.
    
    Args:
        list1: First list
        list2: Second list
        list3: Third list
    
    Returns:
        int: Number of positions where all three lists have the same item
    """
    if not list1 or not list2 or not list3:
        return 0
    
    min_len = min(len(list1), len(list2), len(list3))
    count = 0
    for i in range(min_len):
        if list1[i] == list2[i] == list3[i]:
            count += 1
    return count
