def word_frequency(text):
    # Plausible but wrong: splits on whitespace only, so punctuation stays attached to words.
    counts = {}
    for word in text.lower().split():
        counts[word] = counts.get(word, 0) + 1
    return counts
