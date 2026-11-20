def large_product(nums1, nums2, N):
    """
    Return top N products from nums1 and nums2.
    Handle N exceeding possible pairs by returning all.
    Sort descending.
    Return empty list if inputs empty or N is zero.
    """
    if not nums1 or not nums2 or N <= 0:
        return []
    
    # Generate all products
    products = []
    for a in nums1:
        for b in nums2:
            products.append(a * b)
    
    # Sort descending
    products.sort(reverse=True)
    
    # Return top N
    return products[:N]
