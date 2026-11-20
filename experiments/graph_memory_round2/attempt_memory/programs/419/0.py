def round_and_sum(list1):
    rounded = [round(x) for x in list1]
    total = sum(rounded) * len(list1)
    print(total)
    return total
