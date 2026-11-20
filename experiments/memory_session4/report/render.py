"""Run the bundled renderer on Windows with a dedicated D-drive LibreOffice and temp area."""
from pathlib import Path
import os
import runpy
import sys
import tempfile
ROOT=Path(__file__).resolve().parent
BUNDLE=Path("C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies")
SCRIPT=Path("C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/documents/26.1116.12010/skills/documents/render_docx.py")
OFFICE=Path("D:/CodexResearch/x20-office-renderer/program")
assert (OFFICE/"soffice.exe").exists()
# Portable LibreOffice's help-package extension registration creates temporary directories
# asynchronously. On long Windows paths, cleanup races with these writes after PNG output.
# The rendered PDF/PNGs remain validated; only the disposable working profile is best effort.
original=tempfile.TemporaryDirectory
class CleanupProfile(original):
    def __init__(self,*args,**kwargs):
        kwargs["ignore_cleanup_errors"]=True
        super().__init__(*args,**kwargs)
tempfile.TemporaryDirectory=CleanupProfile
os.environ["PATH"]=str(OFFICE)+os.pathsep+str(BUNDLE/"native/poppler/Library/bin")+os.pathsep+os.environ["PATH"]
os.environ["TEMP"]=os.environ["TMP"]=str(ROOT/"temp")
tempfile.tempdir=str(ROOT/"temp")
folder=ROOT/sys.argv[1]
sys.argv=[str(SCRIPT),str(folder/"agent-memory-session4-results.docx"),"--output_dir",str(folder),"--emit_pdf","--dpi","120"]
runpy.run_path(str(SCRIPT),run_name="__main__")

