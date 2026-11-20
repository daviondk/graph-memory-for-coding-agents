"""Save the research report in a text format suitable for future runs and copying numeric results."""
from pathlib import Path
import re,shutil
D=Path(__file__).resolve().parent
if __name__=="__main__":
    sections=[]
    for path in sorted((D/"pages").glob("*.md")):
        lines=path.read_text("utf8").splitlines();out=[];table=0
        for line in lines:
            if line.startswith("@ "):table=1;out.append("");continue
            if line.startswith("|"):
                out.append(line)
                if table==1:out.append("|"+"|".join("---" for _ in line.strip().strip("|").split("|"))+"|")
                table+=1;continue
            table=0
            if line.startswith("! "):line="![Разница исходов и 95% интервалы]("+line[2:]+")"
            if line.startswith("~ "):line=line[2:]
            out.extend(["",line])
        sections.append("\n".join(out))
    (D/"artifact.md").write_text("\n\n---\n\n".join(sections)+"\n",encoding="utf8")

