"""Stream one top-level JSON array using bounded memory."""
import io
import json

def iter_array(binary,chunk_size=1024*1024):
    stream=io.TextIOWrapper(binary,encoding="utf8")
    decoder=json.JSONDecoder()
    buf=stream.read(chunk_size);pos=0

    def peek():
        nonlocal buf,pos
        while True:
            while pos<len(buf) and buf[pos].isspace():
                pos+=1
            if pos<len(buf):
                return buf[pos]
            buf=stream.read(chunk_size);pos=0
            if not buf:
                return ""

    assert peek()=="[";pos+=1
    if peek()=="]":
        return
    while True:
        while True:
            try:
                item,end=decoder.raw_decode(buf,pos)
                break
            except json.JSONDecodeError:
                extra=stream.read(chunk_size)
                if not extra:
                    raise
                buf=buf[pos:]+extra;pos=0
        pos=end
        yield item
        next_char=peek();pos+=1
        if next_char=="]":
            assert not peek()
            return
        assert next_char=="," and peek()
