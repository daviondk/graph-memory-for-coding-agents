"""Render the distribution of first-position scores for the 128 locked assignments."""
import csv
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

root = Path(__file__).resolve().parent
with (root / "within_per_seed.csv").open(encoding="utf8") as stream:
    rows = list(csv.DictReader(stream))
series = {}
for scope in ("across", "within"):
    series[scope] = Counter(int(r["match1"]) for r in rows if r["same_repo_only"] == "0" and r["control"] == scope)
    assert sum(series[scope].values()) == 64
scores = range(50, 66)
fig, ax = plt.subplots(figsize=(7.5, 2.05))
for slug, title, color, shift in (("across","Любые карточки","#91b6ca",-.19),("within","Внутри проекта","#205772",.19)):
    ax.bar([x+shift for x in scores],[series[slug][x] for x in scores],width=.35,
           color=color,edgecolor=color,linewidth=.45,label=title,zorder=3)
ax.axvline(61,linestyle=(0,(4,2)),color="#574f42",linewidth=1,zorder=1)
ax.axvline(64,linestyle="-",color="#923b29",linewidth=1.4,zorder=1)
ax.set_xticks([51,53,55,57,59,61,64])
ax.set_xlim(49.9,65.1)
ax.yaxis.set_major_locator(MaxNLocator(4,integer=True))
ax.set_ylabel("Перестановок",fontsize=9)
ax.set_xlabel("Правильных первых записей из 99",fontsize=9)
ax.legend(loc="upper right",ncol=2,bbox_to_anchor=(.97,1.17),frameon=False,fontsize=8)
ax.spines[["top","right"]].set_visible(False)
ax.spines[["left","bottom"]].set_color("#87929b")
ax.tick_params(labelsize=8,colors="#253b48",length=3)
ax.grid(axis="y",color="#dae4e9",linewidth=.65,zorder=0)
fig.subplots_adjust(left=.10,right=.985,top=.85,bottom=.27)
fig.savefig(root/"permutation_scores.png",dpi=220,facecolor="white",metadata={"Description":"Observed score distribution over 64 assignments in each of two donor schemes."})

