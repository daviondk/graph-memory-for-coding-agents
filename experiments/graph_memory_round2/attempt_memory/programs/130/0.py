def max_occurrences(nums):
    """
    Find the item with maximum frequency in a given list.
    
    Args:
        nums: A list of elements.
        
    Returns:
        The element with the highest frequency. If there are ties,
        returns the first one encountered with the maximum frequency.
    """
    if not nums:
        return None
    
    freq = {}
    for num in nums:
        freq[num] = freq.get(num, 0) + 1
    
    max_count = 0
    result = None
    for num in nums:
        if freq[num] > max_count:
            max_count = freq[num]
            result = num
    
    return result
