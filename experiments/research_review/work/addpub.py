from collect import root, raw, fetch
import re,json
from bs4 import BeautifulSoup
pdir=root/'pub'
def put(i,**k):
    old=json.loads((raw/(i+'.json')).read_text('utf-8'))
    d={'title':old['title'],'authors':old['authors'],'type':'proceedings-article','date':[2026],**k}
    (pdir/(i+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
put('2308.10144',venue='Proceedings of the AAAI Conference on Artificial Intelligence',date=[2024],doi='10.1609/aaai.v38i17.29936',url='https://ojs.aaai.org/index.php/AAAI/article/view/29936')
put('2409.07429',venue='Proceedings of the 42nd International Conference on Machine Learning',date=[2025],doi=None,url='https://proceedings.mlr.press/v267/wang25bx.html')
put('2610.35089',venue='Vicinagearth',type='journal-article',date=[2026],doi='10.1007/s44336-026-00044-1',url='https://link.springer.com/article/10.1007/s44336-026-00044-1')
put('2102.09692',venue='Proceedings of the ACM on Human-Computer Interaction',type='journal-article',date=[2021],doi='10.1145/3449287',url='https://doi.org/10.1145/3449287')
put('2402.17753',venue='Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)',date=[2024],doi='10.18653/v1/2024.acl-long.747',url='https://aclanthology.org/2024.acl-long.747/',bib=fetch('https://aclanthology.org/2024.acl-long.747.bib').decode())

