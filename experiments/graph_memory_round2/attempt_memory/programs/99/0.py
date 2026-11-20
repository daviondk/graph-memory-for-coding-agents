def decimal_to_binary(n: int) -> str:
    """
    Convert a decimal number to its binary equivalent as a string with no leading zeros.
    
    Args:
        n: A decimal integer (can be negative, zero, or positive)
        
    Returns:
        A string representing the binary equivalent of the input number.
        For negative numbers, a '-' sign is prepended to the binary representation of the absolute value.
    """
    if n == 0:
        return "0"
    
    negative = n < 0
    n = abs(n)
    
    binary_digits = []
    while n > 0:
        binary_digits.append(str(n % 2))
        n //= 2
    
    binary_str = ''.join(reversed(binary_digits))
    
    if negative:
        return '-' + binary_str
    return binary_str
