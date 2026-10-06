def is_balanced(text):
    # Plausible but wrong: only compares counts, so it ignores nesting order.
    return all(text.count(a) == text.count(b) for a, b in ("()", "[]", "{}"))
