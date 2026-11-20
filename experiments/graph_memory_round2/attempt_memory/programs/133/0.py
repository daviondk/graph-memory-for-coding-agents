def sum_negativenum(nums):
    """
    Calculate the sum of the negative numbers in a given list of numbers.
    
    Args:
        nums: A list of numbers.
        
    Returns:
        The sum of all negative numbers in the list.
    """
    return sum(num for num in nums if num < 0)
