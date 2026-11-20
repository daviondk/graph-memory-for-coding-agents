import math

def next_Perfect_Square(N):
    """
    Find the next perfect square greater than the given number N.
    
    Args:
        N: A number (int or float)
        
    Returns:
        The next perfect square greater than N
    """
    # Find the smallest integer whose square is greater than N
    # We need the smallest integer k such that k^2 > N
    # k = floor(sqrt(N)) + 1
    if N < 0:
        # For negative numbers, the next perfect square greater than N is 0 (0^2)
        # But typically we consider non-negative perfect squares
        # Let's handle it: the smallest perfect square > N for N < 0 is 0
        return 0
    
    # Compute the integer square root
    root = math.isqrt(N) if isinstance(N, int) else int(math.isqrt(int(N)))
    
    # Check if root^2 is already greater than N
    # Actually, we want the next perfect square strictly greater than N
    # So we need the smallest k such that k^2 > N
    # k = floor(sqrt(N)) + 1, but if N is a perfect square, we still need the next one
    
    # Let's compute k = floor(sqrt(N)) + 1
    k = root + 1
    # But if N is not an integer, we need to be careful
    # Let's just use: k = floor(sqrt(N)) + 1
    # For N = 15, sqrt(15) ≈ 3.87, floor = 3, k = 4, 4^2 = 16 > 15 ✓
    # For N = 16, sqrt(16) = 4, floor = 4, k = 5, 5^2 = 25 > 16 ✓
    # For N = 0, sqrt(0) = 0, floor = 0, k = 1, 1^2 = 1 > 0 ✓
    
    return k * k
