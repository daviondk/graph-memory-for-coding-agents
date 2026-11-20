import math

def next_Perfect_Square(N: int) -> int:
    """
    Return the smallest perfect square strictly greater than N.
    Handle N as integer. Return -1 if N is negative or no such square exists.
    """
    if N < 0:
        return -1
    
    # Find the smallest integer k such that k^2 > N
    # k = floor(sqrt(N)) + 1
    k = math.isqrt(N)
    if k * k > N:
        # This shouldn't happen with isqrt, but just in case
        return k * k
    else:
        k += 1
        return k * k
