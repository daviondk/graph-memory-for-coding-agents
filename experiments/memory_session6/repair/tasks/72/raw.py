def dif_Square(n):
    """
    Check whether the given number can be represented as difference of two squares.
    
    A number n can be represented as a^2 - b^2 if and only if n is not congruent to 2 mod 4.
    That is, n % 4 != 2.
    
    For negative numbers, we consider the absolute value since a^2 - b^2 can be negative
    if b > a. So we check if |n| can be represented as difference of two squares.
    """
    n = abs(n)
    return n % 4 != 2
