def dif_Square(n):
    """
    Check whether the given number can be represented as the difference of two squares.
    
    A number n can be expressed as a^2 - b^2 if and only if n is not congruent to 2 mod 4.
    That is, n % 4 != 2.
    
    Note: For negative numbers, we consider the absolute value since a^2 - b^2 can be negative.
    Actually, let's think more carefully. a^2 - b^2 = (a-b)(a+b). For any integer n,
    we can write n = a^2 - b^2 if and only if n is not of the form 4k+2.
    
    This holds for all integers n (positive, negative, or zero).
    """
    # A number can be represented as difference of two squares iff it is not congruent to 2 mod 4
    return n % 4 != 2
