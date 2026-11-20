def recursive_list_sum(data_list):
    total = 0
    for item in data_list:
        if isinstance(item, list):
            total += recursive_list_sum(item)
        else:
            total += item
    return total
