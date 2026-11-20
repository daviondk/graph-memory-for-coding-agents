import math

def otherside_rightangle(w, h):
    """
    Find the third side of a right angled triangle.
    
    Given two sides w and h of a right angled triangle, this function
    determines the third side. It assumes that w and h are the two legs
    of the right triangle, and returns the hypotenuse.
    
    If one of the values is the hypotenuse (i.e., the largest side),
    the function will compute the missing leg.
    
    Parameters:
    w (float): One side of the right triangle
    h (float): Another side of the right triangle
    
    Returns:
    float: The third side of the right triangle
    """
    # If both are legs, return hypotenuse
    # If one is hypotenuse and one is a leg, return the other leg
    # We need to determine which case we're in.
    # The problem says "find the third side", so we assume w and h are two sides.
    # The third side could be the hypotenuse (if w and h are legs) or a leg (if one of w/h is hypotenuse).
    
    # A common interpretation: w and h are the two legs, return hypotenuse.
    # But let's handle both cases: if the larger of w, h is the hypotenuse, compute the other leg.
    # Actually, the simplest and most common interpretation is that w and h are the two legs.
    
    # Let's go with: w and h are the two legs, return the hypotenuse.
    return math.sqrt(w ** 2 + h ** 2)
