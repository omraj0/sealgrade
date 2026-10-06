def is_valid_ipv4(text):
    # Plausible but wrong: allows leading zeros and does not reject numbers above 255 with 4+ digits.
    parts = text.split(".")
    return len(parts) == 4 and all(p.isdigit() and int(p) < 1000 for p in parts)
