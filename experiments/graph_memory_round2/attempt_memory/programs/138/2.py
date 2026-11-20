def is_Sum_Of_Powers_Of_Two(n):
    """
    Check whether the given number can be represented as sum of non-zero powers of 2.
    
    A number can be represented as a sum of distinct non-zero powers of 2 if and only if
    its binary representation has no consecutive 1s. This is because each power of 2
    can be used at most once (like in binary representation), and we want to check if
    the binary representation has no adjacent 1s.
    
    Actually, let me reconsider. The question is whether n can be represented as a sum
    of non-zero powers of 2. Since every positive integer can be represented as a sum
    of distinct powers of 2 (its binary representation), the answer would always be True
    for positive n. But wait - maybe the question means that the powers of 2 used must
    be non-zero (i.e., 2^1, 2^2, 2^3, ... not 2^0 = 1). So we cannot use 1 in the sum.
    
    So the question becomes: can n be represented as a sum of distinct powers of 2 where
    none of them is 2^0 = 1? This means the binary representation of n must have the
    least significant bit as 0 (n must be even), and the rest can be any combination.
    
    Wait, but we can use 2^1, 2^2, etc. So n must be representable using only 2, 4, 8, 16, ...
    This means n must be even, and n/2 must be representable as a sum of distinct powers of 2
    starting from 2^0. But any
