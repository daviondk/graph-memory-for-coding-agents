"""Check PDF page geometry and make contact sheets from the verified DOCX render."""
from pathlib import Path
import sys
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

folder = Path(sys.argv[1])
pdf = pdfium.PdfDocument(next(folder.glob('*.pdf')))
print(len(pdf), 'pages')
for number, page in enumerate(pdf, 1):
    contents = page.get_textpage()
    text = contents.get_text_bounded()
    assert '\ufffd' not in text and len(text.split()) >= 80, (number, len(text.split()))
    for index in range(contents.count_chars()):
        if not contents.get_text_range(index, 1).strip():
            continue
        left, bottom, right, top = contents.get_charbox(index)
        assert -1 <= left <= right <= page.get_width() + 1, (number, index)
        assert -1 <= bottom <= top <= page.get_height() + 1, (number, index)
for start in range(0, len(pdf), 6):
    sheet = Image.new('RGB', (1080, 1000), '#dce1e3')
    labels = ImageDraw.Draw(sheet)
    for index in range(min(6, len(pdf) - start)):
        number = start + index + 1
        with Image.open(folder / f'page-{number}.png') as page_image:
            page_image.thumbnail((322, 456))
            x = (index % 3) * 360 + 13
            y = (index // 3) * 500 + 15
            sheet.paste(page_image, (x, y))
            labels.text((x, y + 460), str(number), fill='black')
    sheet.save(folder / f'review-{start + 1}.jpg', quality=88)
