def remove_odd(l):
    """
    Remove odd integers from input list. Return new list preserving order.
    Handle empty lists and non-integer elements gracefully.
    """
    result = []
    for item in l:
        if isinstance(item, int) and not isinstance(item, bool):
            if item % 2 == 0:
                result.append(item)
        else:
            # Non-integer elements are kept as-is (gracefully handled)
            result.append(item)
    return result
