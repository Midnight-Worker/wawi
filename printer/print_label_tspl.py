# print_label_tspl.py
tspl_cmd = """
SIZE 100 mm, 150 mm
GAP 3 mm, 0 mm
DENSITY 8
SPEED 4
DIRECTION 1
CLS
TEXT 50,50,"3",0,1,1,"Artikel: {name}"
TEXT 50,100,"3",0,1,1,"Preis: {price}"
BARCODE 50,160,"128",100,1,0,2,2,"{barcode}"
PRINT 1,1
"""

label = tspl_cmd.format(
    name="Widget X",
    price="9.99 EUR",
    barcode="123456789012"
)

with open("/dev/usb/lp0", "wb") as f:
    f.write(label.encode("ascii"))

