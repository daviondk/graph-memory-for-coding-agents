def replace_list(list1, list2):
    if not list1:
        return list2
    return list1[:-1] + list2
