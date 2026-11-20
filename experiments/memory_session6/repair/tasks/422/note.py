def find_Average_Of_Cube(n):
    """
    Return the average of the cubes of the first n natural numbers.
    
    The first n natural numbers are 1, 2, 3, ..., n.
    The average of their cubes is (1^3 + 2^3 + ... + n^3) / n.
    
    If n == 0, return 0 to avoid division by zero.
    
    Args:
        n: A non-negative integer representing the count of natural numbers.
        
    Returns:
        The average of the cubes as a float (or int if the result is an integer).
    """
    if n == 0:
        return 0
    
    # Sum of cubes formula: (n * (n + 1) / 2) ** 2
    sum_of_cubes = (n * (n + 1) // 2) ** 2
    average = sum_of_cubes / n
    
    # Return int if the result is a whole number, otherwise float
    if average == int(average):
        return int(average)
    return average
