def tuple_to_int(nums):
    """
    Convert a tuple of positive integers into a single integer by concatenating their digits.
    
    Args:
        nums: A tuple of positive integers.
        
    Returns:
        An integer formed by concatenating the digits of the integers in the tuple.
    """
    if not nums:
        return 0
    result = 0
    for num in nums:
        result = result * (10 ** len(str(num))) + num
    return result
