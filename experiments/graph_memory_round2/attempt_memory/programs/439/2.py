def multiple_to_single(L):
    result = 0
    for num in L:
        result = result * 10 ** len(str(abs(num))) + num
    return result
