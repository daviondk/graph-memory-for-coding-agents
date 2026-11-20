def cube_Sum(n):
    """
    Calculate the cube sum of the first n even natural numbers.
    
    The first n even natural numbers are: 2, 4, 6, ..., 2n
    Their cubes are: 2^3, 4^3, 6^3, ..., (2n)^3
    
    The sum is: 8 * (1^3 + 2^3 + ... + n^3)
    We know that 1^3 + 2^3 + ... + n^3 = (n*(n+1)//2)^2
    
    So the cube sum = 8 * (n*(n+1)//2)^2
    """
    if n <= 0:
        return 0
    # Sum of cubes of first n natural numbers: (n*(n+1)//2)^2
    sum_cubes = (n * (n + 1) // 2) ** 2
    # Each even number is 2*i, so cube is 8*i^3
    return 8 * sum_cubes
