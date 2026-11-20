from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent
fp=[D/x for x in ("PROTOCOL_RU.md","selection.json","selection_receipt.json","select_followup.py","acquire_followup.py","writer_followup.py","transfer_followup.py","generate.py","verify_controls.py")]
fp.extend([D.parent/"real_swe"/"acquire.py",D.parent/"serialized_writer"/"writer.py",D.parent/"serialized_writer"/"method_lock.json"])
assert not (D/"results.json").exists() and not any(D.glob("cuts_*"))
(D/"frozen_before_scoring.json").write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in fp},indent=1))

