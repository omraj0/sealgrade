def flatten(items):
    # Plausible but wrong: flattens only one level of nesting and does not validate.
    out = []
    for element in items:
        if isinstance(element, list):
            out.extend(element)
        else:
            out.append(element)
    return out
