def order_by_points(nums):
    def digits_sum(n):
        return sum(int(d) for d in str(abs(n)))
    return sorted(nums, key=digits_sum)
