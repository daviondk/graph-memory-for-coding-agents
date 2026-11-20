def dif_Square(n):
    """
    Return boolean indicating if n equals a² - b² for integers a, b.
    
    A number n can be expressed as a² - b² = (a-b)(a+b) if and only if
    n is not congruent to 2 mod 4.
    
    For negative inputs and zero:
    - 0 = 0² - 0², so True
    - Negative numbers: a² - b² can be negative if b > a.
      For example, -3 = 1² - 2² = 1 - 4 = -3.
      In general, n = a² - b² iff n is not congruent to 2 mod 4.
      This holds for all integers n.
    """
    # n = a² - b² = (a-b)(a+b)
    # Let x = a-b, y = a+b. Then x*y = n, and x and y have the same parity
    # (since a = (x+y)/2 and b = (y-x)/2 must be integers).
    # x and y have the same parity iff x+y is even, i.e., x and y are both even or both odd.
    # If x and y are both odd, then n = x*y is odd.
    # If x and y are both even, then n = x*y is divisible by 4.
    # So n must be odd or divisible by 4.
    # Equivalently, n is NOT congruent to 2 mod 4.
    
    # For negative n, we need to be careful with mod.
    # In Python, n % 4 gives a result in [0, 3] for any integer n.
    # n ≡ 2 (mod 4) means n % 4 == 2.
    
    return n % 4 != 2
