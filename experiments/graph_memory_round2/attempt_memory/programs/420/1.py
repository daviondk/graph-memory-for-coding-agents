def cube_Sum(n):
    if n <= 0:
        return 0
    # First n even natural numbers: 2, 4, 6, ..., 2n
    # Sum of cubes = sum_{k=1}^{n} (2k)^3 = 8 * sum_{k=1}^{n} k^3
    # sum_{k=1}^{n} k^3 = (n(n+1)/2)^2
    s = n * (n + 1) // 2
    return 8 * s * s
