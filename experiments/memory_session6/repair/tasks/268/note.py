def find_star_num(n):
    """
    Return the n-th star number.
    
    Star numbers are centered hexagonal numbers, given by the formula:
    S(n) = 6 * n * (n - 1) + 1 for n >= 1
    S(0) = 0
    
    The sequence starts: 0, 1, 7, 19, 37, 61, 91, ...
    """
    if n == 0:
        return 0
    return 6 * n * (n - 1) + 1
