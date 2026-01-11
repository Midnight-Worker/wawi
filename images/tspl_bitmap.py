# tspl_bitmap.py
from PIL import Image

def load_1bit_bitmap(path_1bit_png: str, invert: bool=False):
    img = Image.open(path_1bit_png).convert("1")
    if invert:
        img = img.point(lambda p: 255 if p == 0 else 0, mode="1")
    width_px, height_px = img.size
    bytes_per_row = (width_px + 7) // 8
    raw = img.tobytes()
    return width_px, height_px, bytes_per_row, raw

def tspl_bitmap_bytes(path_1bit_png: str, x: int, y: int, invert: bool=False) -> bytes:
    width_px, height_px, bytes_per_row, raw = load_1bit_bitmap(path_1bit_png, invert=invert)
    header = f"BITMAP {x},{y},{bytes_per_row},{height_px},0,".encode("ascii")
    return header + raw + b"\n"

