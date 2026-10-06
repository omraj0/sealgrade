Create `/work/solution.py` that defines `slugify(text: str) -> str`.

The function turns arbitrary text into a URL slug:

- accented Latin letters are reduced to their plain ASCII form (`é` becomes `e`)
- characters that cannot be reduced to ASCII are dropped
- everything is lower-case
- every run of characters that are not ASCII letters or digits becomes a single `-`
- the result never starts or ends with `-`
- text with nothing usable returns an empty string

Examples: `slugify("Hello, World!")` is `"hello-world"`, and `slugify("  Crème brûlée  ")` is `"creme-brulee"`.

Use only the Python standard library.
