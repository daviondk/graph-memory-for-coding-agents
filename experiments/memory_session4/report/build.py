from layout import *
from core_pages import core_pages
from tail_pages import tail_pages
import sys
folder=HERE/(sys.argv[1] if len(sys.argv)>1 else 'preview')
folder.mkdir(exist_ok=True)
core_pages()
if (HERE/'handoff_pages.py').exists():
    from handoff_pages import handoff_pages
    handoff_pages()
tail_pages()
doc.save(folder/'agent-memory-session4-results.docx')
print(folder/'agent-memory-session4-results.docx')

