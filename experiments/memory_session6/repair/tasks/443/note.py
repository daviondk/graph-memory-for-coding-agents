def largest_neg(list1):
    negatives = [x for x in list1 if x < 0]
    if not negatives:
        raise ValueError("No negative numbers exist in the list")
    return max(negatives)
