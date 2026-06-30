from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path('assets/resin_society_r_chat_avatar.png')
size = 512
bg = '#111111'
img = Image.new('RGB', (size, size), bg)
d = ImageDraw.Draw(img)
font_paths = [
    r'C:\Windows\Fonts\arialbd.ttf',
    r'C:\Windows\Fonts\segoeuib.ttf',
    r'C:\Windows\Fonts\calibrib.ttf',
]
font = None
for path in font_paths:
    try:
        font = ImageFont.truetype(path, 330)
        break
    except Exception:
        pass
if font is None:
    font = ImageFont.load_default()
text = 'R'
bbox = d.textbbox((0, 0), text, font=font)
w = bbox[2] - bbox[0]
h = bbox[3] - bbox[1]
x = (size - w) / 2 - bbox[0]
y = (size - h) / 2 - bbox[1] - 10
d.text((x, y), text, font=font, fill='#ffffff')
# subtle inner border for crop definition
border = 14
d.rounded_rectangle((border, border, size-border, size-border), radius=72, outline='#2a2a2a', width=8)
img.save(out, 'PNG')
print(out.resolve())