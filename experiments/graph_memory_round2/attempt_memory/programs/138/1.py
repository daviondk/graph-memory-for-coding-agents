def is_Sum_Of_Powers_Of_Two(n):
    if n <= 0:
        return False
    # A number can be represented as sum of non-zero powers of 2 (i.e., 2^1, 2^2, 2^3, ...)
    # if and only if it is greater than 0 and its binary representation does not have a '1' in the least significant bit position (i.e., it's even) OR
    # wait, let me think again.
    # Non-zero powers of 2: 2^1 = 2, 2^2 = 4, 2^3 = 8, ...
    # So we can use 2, 4, 8, 16, ... but NOT 1 (which is 2^0).
    # So the question is: can n be written as a sum of distinct powers of 2, none of which is 2^0?
    # In binary, this means the bit at position 0 (the 1's place) must be 0.
    # So n must be even and n > 0.
    # Wait, but what about n=2? 2 = 2^1, yes.
    # n=3? 3 = 2 + 1, but 1 is 2^0, which is not allowed. So 3 cannot be represented.
    # n=4? 4 = 2^2, yes.
    # n=5? 5 = 4 + 1, 1 is not allowed. So no.
    # n=6? 6 = 4 + 2, both are non-zero powers. Yes.
    # So the condition is:
