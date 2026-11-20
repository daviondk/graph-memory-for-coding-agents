def prime_fib(n: int):
    import math

    def is_prime(p):
        if p < 2:
            return False
        if p == 2:
            return True
        if p % 2 == 0:
            return False
        for k in range(3, int(math.sqrt(p)) + 1, 2):
            if p % k == 0:
                return False
        return True

    a, b = 0, 1
    count = 0
    while True:
        a, b = b, a + b
        if is_prime(b):
            count += 1
            if count == n:
                return b
