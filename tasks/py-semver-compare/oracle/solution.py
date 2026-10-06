import re

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?")


def _parse(value):
    if not isinstance(value, str):
        raise ValueError("version must be a string")
    match = _VERSION.fullmatch(value)
    if match is None:
        raise ValueError("malformed version")
    major, minor, patch, pre = match.groups()
    return (int(major), int(minor), int(patch)), pre


def compare_versions(a, b):
    (nums_a, pre_a), (nums_b, pre_b) = _parse(a), _parse(b)
    if nums_a != nums_b:
        return -1 if nums_a < nums_b else 1
    if pre_a == pre_b:
        return 0
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1
    return -1 if pre_a < pre_b else 1
