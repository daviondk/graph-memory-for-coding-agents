def amicable_numbers_sum(limit):
    if limit < 2:
        return 0
    
    # Compute sum of proper divisors for all numbers up to limit
    sum_of_divisors = [0] * (limit + 1)
    for i in range(1, limit + 1):
        for j in range(2 * i, limit + 1, i):
            sum_of_divisors[j] += i
    
    # Find all amicable numbers and sum them (avoid double counting)
    amicable_sum = 0
    for a in range(2, limit + 1):
        b = sum_of_divisors[a]
        if b > a and b <= limit and sum_of_divisors[b] == a:
            amicable_sum += a + b
    
    return amicable_sum
