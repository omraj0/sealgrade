def gcd_lcm(a, b):
    for value in (a, b):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("arguments must be positive integers")
    x, y = a, b
    while y:
        x, y = y, x % y
    return [x, a // x * b]
