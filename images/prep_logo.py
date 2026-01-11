# prep_logo.py
from PIL import Image, ImageOps

IN_SVG_PNG = "logo.png"      # vorher aus SVG exportieren
OUT_1BIT  = "logo_1bit.png"  # Ergebnis für Druck

img = Image.open(IN_SVG_PNG)

# Alpha/Transparenz auf WEISS legen (ganz wichtig)
img = img.convert("RGBA")
white = Image.new("RGBA", img.size, (255, 255, 255, 255))
img = Image.alpha_composite(white, img).convert("L")  # Graustufen ohne Alpha

# KEIN Dithering, hartes Threshold
img = img.point(lambda x: 0 if x < 160 else 255, mode="1")  # 160 kannst du variieren
# Alternative ohne Dither explizit:
# img = img.convert("1", dither=Image.Dither.NONE)

img.save(OUT_1BIT)
print("Saved:", OUT_1BIT)

