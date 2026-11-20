def first_Digit(n):
    if n == 0:
        return 0
    n = abs(n)
    while n >= 10:
        n //= 10
    return n
