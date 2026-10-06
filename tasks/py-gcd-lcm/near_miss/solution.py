def gcd_lcm(a, b):
    # Plausible but wrong: the "lcm" is just the product, and nothing is validated.
    x, y = a, b
    while y:
        x, y = y, x % y
    return [x, a * b]
