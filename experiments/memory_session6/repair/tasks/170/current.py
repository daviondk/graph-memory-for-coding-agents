def sum_range_list(list1, m, n):
    """
    Find the sum of numbers in a list within a range specified by two indices.
    
    Parameters:
    list1: The input list of numbers
    m: The start index (inclusive)
    n: The end index (inclusive)
    
    Returns:
    The sum of elements from index m to index n (inclusive)
    """
    return sum(list1[m:n+1])
