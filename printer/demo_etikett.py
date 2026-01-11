# print_box_label_dummy.py
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

DEV = "/dev/usb/lp0"  # ggf. anpassen

def tspl_main_label(box_code: str, location: str, box_label: str, items: list[tuple[str, str]]) -> str:
    # 10cm x 15cm
    lines = []
    lines.append('SIZE 100 mm, 150 mm')
    lines.append('GAP 3 mm, 0 mm')
    lines.append('DENSITY 8')
    lines.append('SPEED 4')
    lines.append('DIRECTION 1')
    lines.append('CLS')

    # Kopf
    lines.append(f'TEXT 40,30,"3",0,2,2,"BOX: {box_code}"')
    lines.append(f'TEXT 40,80,"3",0,1,1,"{location}"')
    if box_label:
        lines.append(f'TEXT 40,115,"3",0,1,1,"{box_label}"')

    # Trennlinie
    lines.append('BAR 40,145,720,3')  # x,y,width,height (Dots; grob ok)

    # Itemliste
    y = 170
    lines.append(f'TEXT 40,{y},"3",0,1,1,"Inhalt:"')
    y += 30

    max_items = 10
    for name, qty in items[:max_items]:
        # Kürzen, damit es nicht aus dem Label läuft
        name = (name[:28] + "..") if len(name) > 30 else name
        lines.append(f'TEXT 60,{y},"3",0,1,1,"- {name} x{qty}"')
        y += 28

    if len(items) > max_items:
        lines.append(f'TEXT 60,{y},"3",0,1,1,"... weitere siehe DB"')

    # Barcode unten
    lines.append('BAR 40,1100,720,3')
    lines.append(f'BARCODE 80,1120,"128",120,1,0,2,2,"{box_code}"')
    lines.append(f'TEXT 80,1250,"3",0,1,1,"{box_code}"')

    lines.append('PRINT 1,1')
    return "\n".join(lines) + "\n"

def main():
    tspl = tspl_main_label(BOX_CODE, LOCATION, BOX_LABEL, ITEMS)
    with open(DEV, "wb") as f:
        f.write(tspl.encode("ascii"))

if __name__ == "__main__":
    main()

