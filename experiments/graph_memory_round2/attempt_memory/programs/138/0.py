def is_Sum_Of_Powers_Of_Two(n):
    """
    Check whether the given number can be represented as sum of non-zero powers of 2.
    Non-zero powers of 2 are: 2^1, 2^2, 2^3, ... = 2, 4, 8, 16, ...
    So we need to check if n can be written as a sum of distinct powers of 2, none of which is 2^0=1.
    This is equivalent to checking if n is even and its binary representation does not have a '1' in the least significant bit.
    Actually, any positive integer can be represented as a sum of distinct powers of 2 (its binary representation).
    The question is whether it can be represented using ONLY non-zero powers, i.e., excluding 2^0 = 1.
    So n must be even (no 1 in the least significant bit).
    """
    if n <= 0:
        return False
    # If n is odd, it requires 2^0 = 1 in its binary representation, so it cannot be represented as sum of non-zero powers of 2.
    if n % 2 == 1:
        return False
    # If n is even, it can be represented as sum of non-zero powers of 2.
    return True
