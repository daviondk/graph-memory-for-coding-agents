def max_occurrences(nums):
    """
    Return the most frequent item in the list.
    Tie-breaking is unspecified (first encountered in case of tie).
    Empty list behavior is undefined.
    """
    if not nums:
        raise ValueError("Empty list")
    
    counts = {}
    for item in nums:
        counts[item] = counts.get(item, 0) + 1
    
    max_count = -1
    result = None
    for item in nums:
        if counts[item] > max_count:
            max_count = counts[item]
            result = item
    
    return result
