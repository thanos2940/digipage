import re
import colorsys

def natural_sort_key(s):
    """
    Key function for natural sorting of strings containing numbers.
    e.g. ['file1.jpg', 'file2.jpg', 'file10.jpg']
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def lighten_color(hex_color, factor=0.1):
    """Lightens a hex color by a given factor."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return hex_color # Return as-is if invalid
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = min(1.0, hls[1] + factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

def darken_color(hex_color, factor=0.1):
    """Darkens a hex color by a given factor."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return hex_color
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = max(0.0, hls[1] - factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))
