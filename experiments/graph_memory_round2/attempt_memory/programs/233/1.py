def lateralsuface_cylinder(r, h):
    """
    Calculate the lateral surface area of a cylinder.
    
    The lateral surface area of a cylinder is given by:
    LSA = 2 * pi * r * h
    
    where:
    - r is the radius of the cylinder
    - h is the height of the cylinder
    
    Edge cases:
    - If r or h is negative, return 0 (or raise an error, but we'll return 0 for simplicity)
    - If r or h is 0, the lateral surface area is 0
    
    Parameters:
    r (float): The radius of the cylinder
    h (float): The height of the cylinder
    
    Returns:
    float: The lateral surface area of the cylinder
    """
    import math
    
    # Handle edge cases: negative values or zero
    if r < 0 or h < 0:
        return 0.0
    
    return 2 * math.pi * r * h
