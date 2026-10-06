# Boundary probe: answers that are not valid JSON numbers.
def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return lambda *args, **kwargs: float("nan")
