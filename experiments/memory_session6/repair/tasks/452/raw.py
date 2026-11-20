def loss_amount(actual_cost, sale_amount):
    """
    Calculate the loss amount if the sale amount is less than the actual cost.
    
    Args:
        actual_cost: The cost price of the item.
        sale_amount: The selling price of the item.
    
    Returns:
        The loss amount if there is a loss, otherwise None.
    """
    if sale_amount < actual_cost:
        return actual_cost - sale_amount
    else:
        return None
