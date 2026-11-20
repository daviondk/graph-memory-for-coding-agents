def square_Sum(n):
    """
    Returns the sum of squares of the first n even natural numbers.
    
    The first n even natural numbers are: 2, 4, 6, ..., 2n
    Their squares are: 4, 16, 36, ..., (2n)^2
    Sum = sum_{k=1}^{n} (2k)^2 = 4 * sum_{k=1}^{n} k^2 = 4 * n(n+1)(2n+1)/6
    """
    if n <= 0:
        return 0
    return 4 * n * (n + 1) * (2 * n + 1) // 6
