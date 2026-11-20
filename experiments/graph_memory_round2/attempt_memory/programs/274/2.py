def even_binomial_Coeff_Sum(n):
    """
    Compute the sum of binomial coefficients C(n, k) for even k.
    For a positive integer n, the sum of even-indexed binomial coefficients
    is 2^(n-1) for n >= 1.
    """
    if n < 1:
        raise ValueError("n must be a positive integer")
    return 2 ** (n - 1)
