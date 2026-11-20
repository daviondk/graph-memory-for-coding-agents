def sum_range_list(list1, m, n):
    """
    Find the sum of the numbers in a list between the indices of a specified range.
    
    Parameters:
    list1: The input list of numbers.
    m: The starting index (inclusive).
    n: The ending index (inclusive).
    
    Returns:
    The sum of elements from index m to index n (inclusive).
    """
    return sum(list1[m:n + 1])
