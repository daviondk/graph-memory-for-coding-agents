def sorted_list_sum(lst):
    new_lst = [s for s in lst if len(s) % 2 == 0]
    new_lst.sort(key=lambda x: (len(x), x))
    return new_lst
