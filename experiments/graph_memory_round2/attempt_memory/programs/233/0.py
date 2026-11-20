def lateralsuface_cylinder(r, h):
    """
    Calculate the lateral surface area of a cylinder.
    
    The lateral surface area of a cylinder is the area of the curved surface,
    excluding the top and bottom circles.
    
    Formula: LSA = 2 * pi * r * h
    
    Parameters:
    r (float): Radius of the cylinder
    h (float): Height of the cylinder
    
    Returns:
    float: Lateral surface area of the cylinder
    """
    import math
    return 2 * math.pi * r * h
