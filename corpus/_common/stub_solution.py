# A stand-in solution that can never be correct: every function the grader asks for returns None.
# Attacks ship this so the only way to a passing verdict is the exploit itself.
def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return lambda *args, **kwargs: None
