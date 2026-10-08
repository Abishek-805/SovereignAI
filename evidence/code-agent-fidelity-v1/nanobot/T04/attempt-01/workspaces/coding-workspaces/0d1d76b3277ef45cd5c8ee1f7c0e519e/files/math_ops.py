def multiply(a, b):
    return a * b


def clamp(value, low, high):
    if low > high:
        raise ValueError("low must be less than or equal to high")
    if value < low:
        return low
    elif value > high:
        return high
    else:
        return value
