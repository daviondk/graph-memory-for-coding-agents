def sum_series(n):
    if n <= 0:
        return 0
    total = 0
    term = n
    while term > 0:
        total += term
        term -= 2
    return total
