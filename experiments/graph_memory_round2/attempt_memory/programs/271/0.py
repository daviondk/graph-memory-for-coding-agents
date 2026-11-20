def even_Power_Sum(n):
    """
    Calculate the sum of the first n even natural numbers raised to the fifth power.
    
    The first n even natural numbers are: 2, 4, 6, ..., 2n
    We compute sum((2i)^5 for i in range(1, n+1))
    """
    return sum((2 * i) ** 5 for i in range(1, n + 1))
