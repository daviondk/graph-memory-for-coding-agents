def amicable_numbers_sum(limit):
    if limit < 2:
        return 0
    # Compute sum of divisors for all numbers up to limit
    sum_of_divs = [0] * (limit + 1)
    for i in range(1, limit + 1):
        for j in range(i * 2, limit + 1, i):
            sum_of_divs[j] += i
    # Find amicable pairs and sum unique amicable numbers within [1, limit]
    amicable = set()
    for a in range(2, limit + 1):
        b = sum_of_divs[a]
        if b > a and b <= limit and sum_of_divs[b] == a:
            amicable.add(a)
            amicable.add(b)
    return sum(amicable)
