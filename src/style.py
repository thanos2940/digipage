import colorsys
from config import THEMES

# Helper functions for color manipulation
def lighten_color(hex_color, factor=0.1):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = min(1.0, hls[1] + factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

def darken_color(hex_color, factor=0.1):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = max(0.0, hls[1] - factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

class DynamicStyle:
    FONT_FAMILY = ('Segoe UI', 'Calibri', 'Helvetica', 'Arial')

    def __init__(self):
        self.theme_name = "Neutral Grey"

    def get_font(self, size=10, weight='normal'):
        return (self.FONT_FAMILY[0], size, weight)

    def load_theme(self, theme_name):
        self.theme_name = theme_name
        theme_data = THEMES.get(theme_name, THEMES["Neutral Grey"])
        for key, value in theme_data.items():
            setattr(self, key, value)

        # Update derived colors
        self.BTN_HOVER_BG = lighten_color(self.BTN_BG, 0.1)
        self.BTN_PRESS_BG = darken_color(self.BTN_BG, 0.1)

Style = DynamicStyle()
Style.load_theme("Neutral Grey") # Load a default theme immediately
