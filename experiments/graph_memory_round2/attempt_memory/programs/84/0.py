def sequence(n):
    if n <= 0:
        raise ValueError("n must be a positive integer")
    if n == 1:
        return 1
    a = [1]
    for i in range(2, n + 1):
        a.append(a[a[i - 2]])
    return a[n - 1]
