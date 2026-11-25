"""Plot preregistered methods' paired Hit@2 contrasts and family bootstrap intervals."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
results = json.loads((root/"results.json").read_bytes())
policies = [("neighbor","Первый результат + сосед"),("signature","Первый + другое число / отрицание"),
            ("bm25","BM25"),("e5","E5-base-v2"),("sham","Первый + случайный кандидат"),
            ("local_fusion","Гибрид с рангом по расстоянию")]
fig, ax = plt.subplots(figsize=(9.4, 4.25))
fig.subplots_adjust(left=.395,right=.96,top=.78,bottom=.20)
fig.text(.035,.93,"Что даёт второе чтение на ContraDoc", fontsize=16, weight="bold", color="#202937")
fig.text(.035,.845,"Разность Hit@2 относительно BM25 + E5 (180/271); 95% интервалы по семействам документов".replace("; ",". "),fontsize=10.1,color="#415162")
for i, (method, label) in enumerate(policies):
    v = results["contrasts"][method+"/hybrid"]
    lo, hi = v["ci95_pp"]
    color = "#994719" if method=="signature" else "#28516e"
    ax.plot([lo,hi],[i,i],lw=2.2,color=color)
    ax.plot(v["delta_pp"],i,marker="o",ms=6,color=color)
ax.set_yticks(range(len(policies)), [label for _, label in policies])
ax.invert_yaxis()
ax.axvline(0,lw=1,color="#737e87",ls="--")
ax.set_xlim(-30,10)
ax.set_xlabel("Изменение, процентные пункты",fontsize=10)
ax.grid(axis="x",alpha=.2)
ax.tick_params(axis="both",length=0,pad=6,labelsize=10)
for spine in ax.spines.values():
    spine.set_visible(False)
fig.savefig(root/"paired-contrasts.png",dpi=145,facecolor="white")
plt.close(fig)

