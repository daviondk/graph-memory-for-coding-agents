def find_star_num(n: int) -> int:
    """
    Find the n'th star number.
    
    Star numbers are centered hexagonal numbers, given by the formula:
    S(n) = 6 * n * (n - 1) + 1
    
    where n is the index (1-based).
    
    For example:
    S(1) = 1
    S(2) = 7
    S(3) = 19
    S(4) = 37
    """
    if n < 1:
        raise ValueError("n must be a positive integer")
    return 6 * n * (n - 1) + 1
