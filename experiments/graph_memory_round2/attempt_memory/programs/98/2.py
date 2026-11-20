def multiply_num(numbers):
    if not numbers:
        return 0
    product = 1
    for n in numbers:
        product *= n
    return product / len(numbers)
