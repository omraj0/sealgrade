def flatten(items):
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    out = []
    stack = [iter(items)]
    while stack:
        for element in stack[-1]:
            if isinstance(element, list):
                stack.append(iter(element))
                break
            if isinstance(element, bool) or not isinstance(element, int):
                raise TypeError("elements must be integers or lists")
            out.append(element)
        else:
            stack.pop()
    return out
