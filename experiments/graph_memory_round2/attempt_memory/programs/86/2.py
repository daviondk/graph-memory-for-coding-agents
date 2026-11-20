def centered_hexagonal_number(n: int) -> int:
    """
    Return the nth centered hexagonal number.
    
    Centered hexagonal numbers are given by the formula:
    3 * n * (n - 1) + 1
    
    where n >= 1.
    """
    if n < 1:
        raise ValueError("n must be a positive integer")
    return 3 * n * (n - 1) + 1
