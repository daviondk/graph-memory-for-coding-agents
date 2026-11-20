"""Publish only the rendered, reviewed fourteen-page report pair."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'final'
OUTPUT = ROOT.parents[2] / 'outputs'
BASENAME = 'agent-memory-session4-results'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    qa = json.loads((SOURCE / 'qa.json').read_text(encoding='utf8'))
    pages = qa['pages']
    assert len(pages) == qa['raster_count'] == 14
    assert all(row['bounds_ok'] for row in pages)
    assert all(len(row['titles']) == 1 for row in pages)
    assert all(130 < row['words'] < 500 for row in pages)
    assert all(row['body_bottom_pt'] < 796 for row in pages)
    assert len(qa['docx_hyperlinks']) == 20
    assert len(PdfReader(SOURCE / (BASENAME + '.pdf')).pages) == 14
    OUTPUT.mkdir(parents=True, exist_ok=True)
    published = []
    for extension in ['.docx', '.pdf']:
        source = SOURCE / (BASENAME + extension)
        target = OUTPUT / source.name
        temporary = target.with_suffix(extension + '.tmp')
        shutil.copyfile(source, temporary)
        assert digest(source) == digest(temporary)
        temporary.replace(target)
        published.append({'path': str(target), 'bytes': target.stat().st_size,
                          'sha256': digest(target)})
    record = {
        'published_utc': datetime.now(timezone.utc).isoformat(),
        'files': published,
        'body_font_points': 11.7,
        'qa_sha256': digest(SOURCE / 'qa.json'),
        'visual_review': {
            'reviewer': '/root/novel4',
            'pages': list(range(1, 15)),
            'result': 'PASS. Every final full-page raster inspected. No clipping, overlaps, blank pages or table overflow.',
            'independent_parent_review_pages': [9, 10, 11, 13]
        }
    }
    (SOURCE / 'published.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
