import heapq
from itertools import product as itertools_product


def large_product(nums1, nums2, N):
    """
    Find the N largest products from two lists, selecting one factor from each list.
    
    Args:
        nums1: First list of numbers
        nums2: Second list of numbers
        N: Number of largest products to return
    
    Returns:
        List of N largest products (in descending order)
    """
    if not nums1 or not nums2 or N <= 0:
        return []
    
    # Generate all possible products
    products = [a * b for a in nums1 for b in nums2]
    
    # Sort in descending order and take the top N
    products.sort(reverse=True)
    
    return products[:N]
