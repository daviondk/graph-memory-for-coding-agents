def multiple_to_single(L):
    if not L:
        return 0
    result = 0
    for num in L:
        if num < 0:
            raise ValueError("Negative integers are not supported")
        # Determine the number of digits in num
        if num == 0:
            digits = 1
        else:
            digits = len(str(num))
        result = result * (10 ** digits) + num
    return result
