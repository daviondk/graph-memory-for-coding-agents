def tuple_to_int(nums):
    """
    Convert a tuple of positive integers into a single integer.
    
    Each element in the tuple is treated as a digit, and the resulting
    integer is formed by concatenating these digits in order.
    
    Args:
        nums: A tuple of positive integers (each between 0 and 9).
        
    Returns:
        A single integer formed by concatenating the digits.
    """
    if not nums:
        return 0
    result = 0
    for num in nums:
        result = result * 10 + num
    return result
