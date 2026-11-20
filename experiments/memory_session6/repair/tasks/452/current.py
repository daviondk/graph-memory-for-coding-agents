def loss_amount(actual_cost, sale_amount):
    """
    Calculate the loss amount on a sale.
    
    If the sale amount is less than the actual cost, return the difference (loss).
    Otherwise, return 0.
    
    Args:
        actual_cost: The original cost of the item.
        sale_amount: The amount for which the item was sold.
    
    Returns:
        The loss amount if there is a loss, otherwise 0.
    """
    if sale_amount < actual_cost:
        return actual_cost - sale_amount
    else:
        return 0
