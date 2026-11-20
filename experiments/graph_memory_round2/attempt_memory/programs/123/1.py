def amicable_numbers_sum(limit):
    if limit < 2:
        return 0
    
    # Compute sum of proper divisors for all numbers up to limit
    sum_divisors = [0] * (limit + 1)
    for i in range(1, limit + 1):
        for j in range(2 * i, limit + 1, i):
            sum_divisors[j] += i
    
    # Find amicable pairs and sum unique numbers
    amicable = set()
    for a in range(2, limit + 1):
        b = sum_divisors[a]
        if b > a and b <= limit and sum_divisors[b] == a:
            amicable.add(a)
            amicable.add(b)
    
    return sum(amicable)
