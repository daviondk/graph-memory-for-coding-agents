def tuple_to_int(nums):
    if not nums:
        return 0
    result = 0
    for n in nums:
        result = result * 10 + n
    return result
