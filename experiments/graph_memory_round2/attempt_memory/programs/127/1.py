def multiply_int(x, y):
    """
    Multiply two integers without using the * operator.
    """
    # Handle negative numbers
    negative = (x < 0) ^ (y < 0)
    x = abs(x)
    y = abs(y)
    
    result = 0
    while y > 0:
        if y % 2 == 1:
            result += x
        x <<= 1
        y >>= 1
    
    if negative:
        result = -result
    return result
