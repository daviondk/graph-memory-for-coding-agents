def square_Sum(n):
    """
    Return sum of squares of first n even natural numbers.
    
    The first n even natural numbers are: 2, 4, 6, ..., 2n
    Sum of squares = 2^2 + 4^2 + 6^2 + ... + (2n)^2
                  = 4 * (1^2 + 2^2 + ... + n^2)
                  = 4 * n(n+1)(2n+1)/6
                  = 2n(n+1)(2n+1)/3
    """
    if n == 0:
        return 0
    return 2 * n * (n + 1) * (2 * n + 1) // 3
