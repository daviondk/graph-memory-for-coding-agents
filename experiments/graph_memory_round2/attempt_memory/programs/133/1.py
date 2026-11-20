def sum_negativenum(nums):
    """
    Calculate the sum of the negative numbers in a given list using a lambda function.
    
    Args:
        nums: A list of numbers.
        
    Returns:
        The sum of all negative numbers in the list.
    """
    return sum(filter(lambda x: x < 0, nums))
