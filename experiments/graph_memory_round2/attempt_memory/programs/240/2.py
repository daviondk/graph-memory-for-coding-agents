def replace_list(list1, list2):
    if not list1:
        return list2.copy()
    result = list1[:-1] + list2
    return result
