def bell_number(n: int) -> int:
    """Compute the Bell number B(n) for non-negative integer n."""
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    if n == 0:
        return 1
    
    # Use Bell triangle (Aitken's array)
    # B(0) = 1
    # Build the triangle row by row
    triangle = [[1]]
    for i in range(1, n + 1):
        row = [triangle[i - 1][-1]]
        for j in range(1, i + 1):
            row.append(row[j - 1] + triangle[i - 1][j - 1])
        triangle.append(row)
    
    return triangle[n][0]
