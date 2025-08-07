import re
from PIL import Image
from PyQt6.QtGui import QImage, QPixmap

def natural_sort_key(s):
    """
    Splits a string into a list of strings and numbers for natural sorting.
    e.g., 'image10.jpg' comes after 'image2.jpg'.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    """
    Converts a Pillow Image to a QPixmap.
    """
    if pil_image.mode == "RGB":
        r, g, b = pil_image.split()
        pil_image = Image.merge("RGB", (b, g, r))
    elif pil_image.mode == "RGBA":
        r, g, b, a = pil_image.split()
        pil_image = Image.merge("RGBA", (b, g, r, a))

    # Convert the PIL image to a QImage
    if pil_image.mode == "RGB":
        img_data = pil_image.tobytes("raw", "RGB")
        qimage = QImage(img_data, pil_image.width, pil_image.height, QImage.Format.Format_RGB888)
    else: # RGBA
        img_data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(img_data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)

    return QPixmap.fromImage(qimage)
