"""Replay selection with observable event fields only and a strict no-label input boundary."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import prepare

D=prepare.D
real_read=prepare.read

def guarded(p):
    if p==prepare.C/"flow-packets.json":
        return [{"trace":r["trace"],"events":[{k:e[k] for k in ("id","symbols","literals","write")} for e in r["events"]]}
                 for r in real_read(p)]
    if p==prepare.OBS/"corpus-audit.json":
        return [{"trace":r["trace"],"family":r["family"]} for r in real_read(p)]
    raise RuntimeError("unexpected mutable or labelled input: "+str(p))

with TemporaryDirectory(dir=prepare.C) as tmp:
    dest=Path(tmp)
    (dest/"PROTOCOL_RU.md").write_bytes((D/"PROTOCOL_RU.md").read_bytes())
    with patch.object(prepare,"read",guarded), patch.object(prepare,"D",dest):
        prepare.main()
    for name in ("cards.json.gz","requests.json.gz","selection-lock.json"):
        assert (dest/name).read_bytes()==(D/name).read_bytes(),name
prepare.write(D/"blind-audit.json",{"selection":prepare.h((D/"selection-lock.json").read_bytes()),"complete_byte_identity":True,
              "allowed_fields":{"trajectory":["trace","events"],"event":["id","symbols","literals","write"],"source_metadata":["trace","family"]}})

