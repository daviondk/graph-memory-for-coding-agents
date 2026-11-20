def count_samepair(list1, list2, list3):
    count = 0
    for a, b, c in zip(list1, list2, list3):
        if a == b == c:
            count += 1
    return count
