def largest_prime_factor(n: int):
    largest = 1
    while n % 2 == 0:
        largest = 2
        n //= 2
    f = 3
    while f * f <= n:
        while n % f == 0:
            largest = f
            n //= f
        f += 2
    if n > 1:
        largest = n
    return largest
