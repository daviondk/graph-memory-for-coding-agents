"""Build real LlamaIndex Document and SentenceWindowNodeParser objects, save offsets."""
from data import *
import os
os.environ['NLTK_DATA']=str(PRIVATE/'bundled-nltk-copy')
from importlib.metadata import version
from llama_index.core import Document
from llama_index.core.node_parser.text.sentence_window import SentenceWindowNodeParser
from llama_index.core.utils import globals_helper
import llama_index.core.node_parser.text.sentence_window as module
from llama_index.core.node_parser.text import utils as splitter
from nltk.tokenize import PunktSentenceTokenizer

def run():
    freeze();co=read(PRIOR/'cohort.json.gz')['panel'];sec={};n=0
    parser=SentenceWindowNodeParser.from_defaults()
    punkt=globals_helper.punkt_tokenizer
    assert type(punkt) is PunktSentenceTokenizer and len(punkt._params.abbrev_types)==0
    assert parser.window_size==3 and version('llama-index-core')=='0.14.26'
    released=Path(module.__file__);up=PRIVATE/'upstream/llama-index-core_llama_index_core_node_parser_text_sentence_window.py'
    assert sha(released)==sha(up)
    for a in read(RAW)['data']:
        title=a['title']
        if title not in co:continue
        s=body(a);assert hashlib.sha256(s.encode()).hexdigest()==co[title]['body_sha']
        spans=list(punkt.span_tokenize(s));spans=[(l,spans[i+1][0] if i+1<len(spans) else len(s)) for i,(l,h) in enumerate(spans)]
        nodes=parser.get_nodes_from_documents([Document(text=s)])
        assert len(nodes)==len(spans)
        hh=hashlib.sha256()
        for i,(node,(l,h)) in enumerate(zip(nodes,spans,strict=True)):
            value=' '.join(s[x:y] for x,y in spans[max(0,i-3):i+4]);meta=node.metadata
            assert node.text==s[l:h] and meta['original_text']==node.text and meta['window']==value
            hh.update(hashlib.sha256(value.encode()).digest())
        sec[title]={'s':spans,'windows':hh.hexdigest()};n+=len(spans)
    assert set(sec)==set(co)
    data=save(D/'sentence-index.json.gz',sec)
    save(D/'native-receipt.json',{'index':data,'articles':len(sec),'sentences':n,'package':version('llama-index-core'),'nltk':version('nltk'),'parser':sha(released),'splitter':sha(Path(splitter.__file__)),'punkt_type':type(punkt).__name__,'abbreviation_types':len(punkt._params.abbrev_types),'metadata_verified_for_every_node':True,'plan':sha(D/'plan.json'),'code':sha(Path(__file__))})
if __name__=='__main__':run()
