def max_product_tuple(list1):
    if not list1:
        return 0
    max_abs = None
    for t in list1:
        if len(t) < 2:
            continue
        prod = 1
        for x in t:
            prod *= x
        abs_prod = abs(prod)
        if max_abs is None or abs_prod > max_abs:
            max_abs = abs_prod
    return max_abs if max_abs is not None else 0
