def round_and_sum(list1):
    rounded = [round(x) for x in list1]
    total = sum(rounded)
    result = total * len(list1)
    print(result)
    return result
