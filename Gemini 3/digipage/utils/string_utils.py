import re

def natural_sort_key(s):
    """
    Key for natural sorting (e.g., 'img1.jpg', 'img2.jpg', 'img10.jpg').
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]