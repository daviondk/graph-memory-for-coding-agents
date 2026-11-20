def decimal_to_binary(n: int) -> str:
    """
    Convert a decimal number to its binary equivalent.
    
    Args:
        n: A decimal integer (positive, negative, or zero)
        
    Returns:
        A string representing the binary equivalent of the decimal number.
        For negative numbers, the string starts with '-'.
    """
    if n == 0:
        return "0"
    
    negative = n < 0
    n = abs(n)
    
    binary_digits = []
    while n > 0:
        binary_digits.append(str(n % 2))
        n //= 2
    
    binary_digits.reverse()
    result = ''.join(binary_digits)
    
    if negative:
        result = '-' + result
    
    return result
