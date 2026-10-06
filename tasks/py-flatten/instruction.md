Create `/work/solution.py` that defines `flatten(items: list) -> list[int]`.

`items` is a list whose elements are integers or further lists of the same kind, nested to any
depth. Return all the integers in the order they appear. An empty list, or lists containing only
empty lists, flatten to `[]`.

Raise `TypeError` if `items` is not a list or if any element is neither an integer nor a list.
Booleans are not integers for this purpose.

Use only the Python standard library.
