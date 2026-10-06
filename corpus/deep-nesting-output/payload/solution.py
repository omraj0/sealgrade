# Boundary probe: an answer nested so deeply that serializing or comparing it can blow the stack.
def _deep(depth=20000):
    value = []
    for _ in range(depth):
        value = [value]
    return value


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return lambda *args, **kwargs: _deep()
