# convert_logo.py
from PIL import Image

img = Image.open("logo.png").convert("L")

# hartes Schwarz/Weiß (Thermodruck!)
img = img.point(lambda x: 0 if x < 128 else 255, "1")

img.save("logo.bmp")

