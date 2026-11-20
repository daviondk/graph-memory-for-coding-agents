def count_nums(arr):
    def digits_sum(n):
        if n < 0:
            return -int(str(n)[1]) + sum(int(d) for d in str(n)[2:])
        return sum(int(d) for d in str(n))
    return len(list(filter(lambda x: x > 0, [digits_sum(i) for i in arr])))
