def compare_versions(a, b):
    # Plausible but wrong: compares the raw strings, so 1.10.0 sorts before 1.9.0.
    return (a > b) - (a < b)
