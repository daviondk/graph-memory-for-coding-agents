import heapq
from itertools import product as itertools_product


def large_product(nums1, nums2, N):
    """
    Find the N largest products from all pairwise products of nums1 and nums2.
    
    Args:
        nums1: List of numbers
        nums2: List of numbers
        N: Number of largest products to return
    
    Returns:
        List of N largest products (in descending order)
    """
    if not nums1 or not nums2 or N <= 0:
        return []
    
    # Generate all pairwise products
    all_products = [a * b for a in nums1 for b in nums2]
    
    # Get the N largest products
    if N >= len(all_products):
        return sorted(all_products, reverse=True)
    else:
        return heapq.nlargest(N, all_products)
