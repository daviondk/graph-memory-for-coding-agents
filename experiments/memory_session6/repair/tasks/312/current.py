import math

def volume_cone(r, h):
    """
    Calculate the volume of a cone.
    
    Parameters:
    r (float): Radius of the cone
    h (float): Height of the cone
    
    Returns:
    float: Volume of the cone
    """
    return (1/3) * math.pi * r**2 * h
