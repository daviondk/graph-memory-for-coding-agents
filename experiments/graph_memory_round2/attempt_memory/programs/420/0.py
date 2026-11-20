def cube_Sum(n):
    """
    Find the cube sum of first n even natural numbers.
    
    The first n even natural numbers are: 2, 4, 6, ..., 2n
    Their cubes are: 2^3, 4^3, 6^3, ..., (2n)^3
    
    The sum is: sum((2k)^3 for k in range(1, n+1))
               = 8 * sum(k^3 for k in range(1, n+1))
               = 8 * (n * (n + 1) // 2) ** 2
    """
    return 8 * (n * (n + 1) // 2) ** 2
