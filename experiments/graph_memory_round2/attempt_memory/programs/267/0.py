def square_Sum(n):
    """
    Returns the sum of the squares of the first n odd natural numbers.
    
    The first n odd natural numbers are: 1, 3, 5, ..., (2n-1)
    The sum of their squares is: 1^2 + 3^2 + 5^2 + ... + (2n-1)^2
    
    There is a closed-form formula: n * (2n - 1) * (2n + 1) / 3
    """
    return n * (2 * n - 1) * (2 * n + 1) // 3
