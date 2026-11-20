def specialFilter(nums):
    count = 0
    for num in nums:
        if num > 10:
            number_as_string = str(num)
            first_digit = int(number_as_string[0])
            last_digit = int(number_as_string[-1])
            if first_digit % 2 != 0 and last_digit % 2 != 0:
                count += 1
    return count
