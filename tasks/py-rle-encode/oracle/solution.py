def rle_encode(text):
    if not isinstance(text, str) or any(ch.isdigit() for ch in text):
        raise ValueError("invalid input")
    out = []
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and text[j] == text[i]:
            j += 1
        out.append(f"{text[i]}{j - i}")
        i = j
    return "".join(out)
