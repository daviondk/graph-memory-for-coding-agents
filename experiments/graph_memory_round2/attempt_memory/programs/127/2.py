def multiply_int(x: int, y: int) -> int:
    """
    Return the product of two integers without using the * operator.
    Handles standard integer multiplication edge cases.
    """
    # Handle zero cases
    if x == 0 or y == 0:
        return 0

    # Determine the sign of the result
    negative = (x < 0) ^ (y < 0)

    # Work with absolute values
    a = abs(x)
    b = abs(y)

    # Ensure a is the smaller number for efficiency (fewer iterations)
    if a > b:
        a, b = b, a

    # Multiply using repeated addition
    result = 0
    for _ in range(a):
        result += b

    return -result if negative else result
