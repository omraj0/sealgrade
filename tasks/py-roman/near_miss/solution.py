def to_roman(n: int) -> str:
    # Plausible but wrong: additive only (4 becomes IIII) and no input validation.
    out = []
    for value, numeral in (
        (1000, "M"),
        (500, "D"),
        (100, "C"),
        (50, "L"),
        (10, "X"),
        (5, "V"),
        (1, "I"),
    ):
        count, n = divmod(n, value)
        out.append(numeral * count)
    return "".join(out)
