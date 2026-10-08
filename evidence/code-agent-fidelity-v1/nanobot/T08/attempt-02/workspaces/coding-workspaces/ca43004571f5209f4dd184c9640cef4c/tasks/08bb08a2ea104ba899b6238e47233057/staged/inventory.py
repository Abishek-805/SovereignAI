items = {}

def set_quantity(item_id, quantity):
    # Reject boolean IDs
    if isinstance(item_id, bool):
        raise ValueError("Boolean IDs are not allowed")
    
    # Reject boolean quantities (bool is subclass of int in Python)
    if isinstance(quantity, bool):
        raise ValueError("Boolean quantities are not allowed")
    
    # Reject negative or non-integer quantities
    if not isinstance(quantity, int) or quantity < 0:
        raise ValueError("Quantity must be a non-negative integer")
    
    # Normalize item_id: convert to int if it's a string representation of an integer
    if isinstance(item_id, str):
        try:
            item_id = int(item_id)
        except ValueError:
            raise KeyError(f"Unknown item ID: {item_id}")
    
    # Check if item exists with the normalized integer key
    if item_id not in items:
        raise KeyError(item_id)
    
    # Update the quantity for the existing item
    items[item_id]["quantity"] = quantity


def label():
    return "warehouse"
