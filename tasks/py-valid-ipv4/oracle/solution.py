def is_valid_ipv4(text):
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    parts = text.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not (part.isascii() and part.isdigit()):
            return False
        if len(part) > 1 and part[0] == "0":
            return False
        if int(part) > 255:
            return False
    return True
