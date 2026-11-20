def big_sum(nums):
    """
    Find the sum of the largest and smallest values in the given array.
    
    Args:
        nums: A list of numbers
        
    Returns:
        The sum of the largest and smallest values in the list
    """
    if not nums:
        return 0
    return max(nums) + min(nums)
