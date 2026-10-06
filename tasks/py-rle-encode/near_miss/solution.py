def rle_encode(text):
    # Plausible but wrong: omits the count when a run has length 1, and skips validation.
    out = []
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and text[j] == text[i]:
            j += 1
        out.append(text[i] + (str(j - i) if j - i > 1 else ""))
        i = j
    return "".join(out)
