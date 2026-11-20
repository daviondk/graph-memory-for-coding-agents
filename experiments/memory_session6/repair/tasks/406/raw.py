def find_Parity(x: int) -> int:
    """
    Find the parity of a given number.
    
    The parity of a number is 1 if the number of set bits (1s) in its binary
    representation is odd, and 0 if the number of set bits is even.
    
    Args:
        x: An integer
        
    Returns:
        1 if the number of set bits is odd, 0 otherwise
    """
    # Count the number of set bits
    count = bin(x & 0xFFFFFFFFFFFFFFFF if x < 0 else x).count('1')
    # Return 1 if count is odd, 0 if even
    return count % 2
