from PIL import Image

DEV = "/dev/usb/lp0"

BOX_CODE = "B000042"
LOCATION = "R4 / S02 / F01"
BOX_LABEL = "Schrauben-Sortiment"

ITEMS = [
    ("Schraube M3x10", "300"),
    ("Schraube M4x20", "200"),
    ("Holzschraube 4x40", "150"),
    ("Unterlegscheibe M3", "500"),
    ("Mutter M3", "400"),
]

def bitmap_to_tspl(path: str, x: int, y: int) -> str:
    img = Image.open(path).convert("1")
    width, height = img.size
    bytes_per_row = (width + 7) // 8
    raw = img.tobytes()
    return (
        f"BITMAP {x},{y},{bytes_per_row},{height},0,{raw.hex().upper()}\n"
    )

def build_label():
    tspl = []
    tspl += [
        "SIZE 100 mm, 150 mm",
        "GAP 3 mm, 0 mm",
        "DENSITY 8",
        "SPEED 4",
        "DIRECTION 1",
        "CLS",
    ]

    # 🖼️ LOGO (oben mittig)
    tspl.append(bitmap_to_tspl("../images/logo.bmp", x=200, y=20))

    # Text
    tspl.append(f'TEXT 40,200,"3",0,2,2,"BOX: {BOX_CODE}"')
    tspl.append(f'TEXT 40,260,"3",0,1,1,"{LOCATION}"')
    tspl.append(f'TEXT 40,300,"3",0,1,1,"{BOX_LABEL}"')

    tspl.append("BAR 40,330,720,3")

    y = 360
    tspl.append(f'TEXT 40,{y},"3",0,1,1,"Inhalt:"')
    y += 30

    for name, qty in ITEMS[:10]:
        tspl.append(f'TEXT 60,{y},"3",0,1,1,"- {name} x{qty}"')
        y += 28

    # Barcode unten
    tspl.append("BAR 40,1100,720,3")
    tspl.append(f'BARCODE 80,1120,"128",120,1,0,2,2,"{BOX_CODE}"')
    tspl.append(f'TEXT 80,1250,"3",0,1,1,"{BOX_CODE}"')

    tspl.append("PRINT 1,1")
    return "\n".join(tspl) + "\n"

def main():
    data = build_label()
    with open(DEV, "wb") as f:
        f.write(data.encode("ascii"))

if __name__ == "__main__":
    main()

