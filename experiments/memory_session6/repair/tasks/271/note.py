def even_Power_Sum(n):
    """
    Return sum of fifth powers of first n even natural numbers.
    Handle n=0 as 0. Assume n is non-negative integer.
    """
    if n == 0:
        return 0
    total = 0
    for i in range(1, n + 1):
        even_num = 2 * i
        total += even_num ** 5
    return total
