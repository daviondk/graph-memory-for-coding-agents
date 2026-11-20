def sum_negativenum(nums):
    return lambda: sum(x for x in nums if x < 0)()
