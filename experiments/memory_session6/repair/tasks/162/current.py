def sum_series(n):
    """
    Calculate the sum (n - 2*i) from i=0 to n // 2,
    i.e., n + (n-2) + (n-4) + ... until the term becomes <= 0.
    """
    total = 0
    i = 0
    while n - 2 * i > 0:
        total += n - 2 * i
        i += 1
    return total
