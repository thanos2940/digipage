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
    Converts a Pillow Image to a QPixmap safely.
    """
    # Convert PIL image to a QImage. Using RGBA is more robust.
    if pil_image.mode != 'RGBA':
        pil_image = pil_image.convert('RGBA')

    img_data = pil_image.tobytes('raw', 'RGBA')
    qimage = QImage(img_data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)

    # The QImage created this way is a wrapper around the python bytes object.
    # We must create a deep copy to ensure the data is owned by the QImage,
    # preventing a segmentation fault when the bytes object goes out of scope.
    return QPixmap.fromImage(qimage.copy())
