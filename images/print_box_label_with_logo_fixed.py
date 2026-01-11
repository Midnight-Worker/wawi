# print_box_label_with_logo_fixed.py
from tspl_bitmap import load_1bit_bitmap, tspl_bitmap_bytes

DEV = "/dev/usb/lp0"

BOX_CODE  = "B000042"
LOCATION  = "R4 / S02 / F01"
BOX_LABEL = "Schrauben-Sortiment"
ITEMS = [
    ("Schraube M3x10", "300"),
    ("Schraube M4x20", "200"),
    ("Holzschraube 4x40", "150"),
    ("Unterlegscheibe M3", "500"),
    ("Mutter M3", "400"),
]

LOGO_1BIT = "../images/logo_1bit.png"

# Labelbreite in Dots: je nach Drucker
# 10 cm ≈ 4 inch
# 203 dpi -> 812 dots (4*203)
# 300 dpi -> 1200 dots (4*300)
LABEL_WIDTH_DOTS = 812   # falls dein Drucker 300dpi hat: 1200

MARGIN_X = 20
MARGIN_Y = 20

def build_label_bytes(invert_logo=False) -> bytes:
    out = b""
    out += b"SIZE 100 mm, 150 mm\nGAP 3 mm, 0 mm\nDENSITY 8\nSPEED 4\nDIRECTION 1\nCLS\n"

    # Logo oben rechts
    logo_w, logo_h, _, _ = load_1bit_bitmap(LOGO_1BIT, invert=invert_logo)
    x = max(0, LABEL_WIDTH_DOTS - logo_w - MARGIN_X)
    y = MARGIN_Y
    out += tspl_bitmap_bytes(LOGO_1BIT, x=x, y=y, invert=invert_logo)

    # Restliches Layout (wie vorher)
    out += f'TEXT 40,200,"3",0,2,2,"BOX: {BOX_CODE}"\n'.encode("ascii")
    out += f'TEXT 40,260,"3",0,1,1,"{LOCATION}"\n'.encode("ascii")
    out += f'TEXT 40,300,"3",0,1,1,"{BOX_LABEL}"\n'.encode("ascii")
    out += b"BAR 40,330,720,3\n"

    yy = 360
    out += f'TEXT 40,{yy},"3",0,1,1,"Inhalt:"\n'.encode("ascii")
    yy += 30
    for name, qty in ITEMS[:10]:
        safe = name.replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
        out += f'TEXT 60,{yy},"3",0,1,1,"- {safe} x{qty}"\n'.encode("ascii")
        yy += 28

    out += b"BAR 40,1100,720,3\n"
    out += f'BARCODE 80,1120,"128",120,1,0,2,2,"{BOX_CODE}"\n'.encode("ascii")
    out += f'TEXT 80,1250,"3",0,1,1,"{BOX_CODE}"\n'.encode("ascii")
    out += b"PRINT 1,1\n"
    return out

def main():
    data = build_label_bytes(invert_logo=False)
    with open(DEV, "wb") as f:
        f.write(data)

if __name__ == "__main__":
    main()

