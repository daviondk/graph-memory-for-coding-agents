def decimal_to_binary(n):
    """
    Convert a non-negative integer n to its binary string representation.
    
    Args:
        n: A non-negative integer.
        
    Returns:
        A string representing the binary form of n, with no leading zeros.
        Returns '0' for zero.
        
    Raises:
        TypeError: If n is not an integer.
        ValueError: If n is negative.
    """
    if not isinstance(n, int):
        raise TypeError("Input must be an integer")
    if n < 0:
        raise ValueError("Input must be non-negative")
    if n == 0:
        return '0'
    return bin(n)[2:]
