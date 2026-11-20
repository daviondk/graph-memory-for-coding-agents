def multiple_to_single(L):
    if not L:
        return 0
    result = 0
    for num in L:
        if num < 0:
            raise ValueError("Negative numbers not supported")
        # Determine the number of digits in num
        digits = len(str(num))
        result = result * (10 ** digits) + num
    return result
