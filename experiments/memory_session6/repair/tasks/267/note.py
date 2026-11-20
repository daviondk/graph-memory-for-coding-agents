def square_Sum(n):
    """
    Return sum of squares of first n odd natural numbers.
    
    The first n odd natural numbers are: 1, 3, 5, ..., (2n-1)
    Sum of squares = 1^2 + 3^2 + 5^2 + ... + (2n-1)^2
    
    There is a known formula: sum of squares of first n odd numbers = n(2n-1)(2n+1)/3
    """
    if n == 0:
        return 0
    return n * (2 * n - 1) * (2 * n + 1) // 3
