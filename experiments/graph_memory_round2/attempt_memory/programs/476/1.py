def big_sum(nums):
    if not nums:
        raise ValueError("Array must not be empty")
    return max(nums) + min(nums)
