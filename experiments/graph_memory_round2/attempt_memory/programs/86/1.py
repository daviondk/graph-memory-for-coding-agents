def centered_hexagonal_number(n):
    """
    Return the nth centered hexagonal number.
    
    The centered hexagonal numbers are given by the formula:
    H(n) = 3n(n-1) + 1 for n >= 1
    
    Edge cases:
    - If n < 1, we can return 0 or raise an error. Here we return 0 for n < 1.
    """
    if n < 1:
        return 0
    return 3 * n * (n - 1) + 1
