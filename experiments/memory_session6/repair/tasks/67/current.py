def bell_number(n: int) -> int:
    """
    Compute the nth Bell number, which counts the number of ways to partition a set of n elements.
    
    Uses dynamic programming with the Bell triangle (Aitken's array) approach.
    """
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    if n == 0:
        return 1
    
    # Build the Bell triangle
    # triangle[i][j] for i from 0 to n, j from 0 to i
    # triangle[0][0] = 1
    # triangle[i][0] = triangle[i-1][i-1]
    # triangle[i][j] = triangle[i][j-1] + triangle[i-1][j-1] for j > 0
    # Bell number B(n) = triangle[n][0]
    
    triangle = [[0] * (n + 1) for _ in range(n + 1)]
    triangle[0][0] = 1
    
    for i in range(1, n + 1):
        triangle[i][0] = triangle[i - 1][i - 1]
        for j in range(1, i + 1):
            triangle[i][j] = triangle[i][j - 1] + triangle[i - 1][j - 1]
    
    return triangle[n][0]
