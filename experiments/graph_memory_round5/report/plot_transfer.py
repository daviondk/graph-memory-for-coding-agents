"""Paired repository bootstrap CIs in percentage points versus always reading the top three."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'graph_memory_round3'/'.plotlibs'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

def read(filename):
    return json.loads((ROOT.parent/'retrieval'/filename).read_bytes())
def main():
    batch=read('transfer_results.json')['groups']
    online=read('online_result.json')['outcomes']
    reserve=read('reserve_result.json')['outcomes']
    labels=['Общая очередь','Очередь внутри Easy и Hard','По одному, резерв до 12 мест','По одному, резерв до 2% квоты']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.unicode_minus':True})
    fig,ax=plt.subplots(figsize=(8.7,4.08))
    for y in (1.5,3.5):
        ax.axhspan(y-.49,y+.49,color='#eef3f7',zorder=0)
    for lang,marker,color,offset in [('java','o','#155b78',.13),('python','D','#a34b12',-.13)]:
        data=[]
        for mode in ('mixed','level'):
            row=batch[lang+'-'+mode]['contrasts']['count_model-fixed']
            data.append((row['delta'],*row['ci']))
        for source in (online,reserve):
            row=source[lang]['stats']['count_model']
            data.append((row['delta_fixed'],*row['cluster_ci']))
        for i,(value,lo,hi) in enumerate(data):
            y=3.5-i+offset
            ax.errorbar(100*value,y,xerr=[[100*(value-lo)],[100*(hi-value)]],fmt=marker,color=color,ecolor=color,markersize=6.7,capsize=4,elinewidth=1.7,label=lang.title() if i==0 else None,zorder=4)
    ax.axvline(0,color='#26374a',linewidth=1.2,zorder=2)
    ax.set_xlim(-5,7.5);ax.set_ylim(0,4.05)
    ax.set_xlabel('Изменение доли запросов с найденным эталоном, п.п.',fontsize=11.4,labelpad=8)
    ax.set_yticks([3.5,2.5,1.5,.5],labels=labels)
    ax.xaxis.set_major_locator(MultipleLocator(2));ax.xaxis.grid(True,color='#becad0',linewidth=.65,alpha=.6)
    ax.tick_params(axis='y',length=0,pad=7);ax.tick_params(axis='x',length=3,color='#8a959a')
    for d in ('left','right','top'):ax.spines[d].set_visible(False)
    ax.spines['bottom'].set_color('#a6b1b6')
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,frameon=False,borderaxespad=0)
    fig.subplots_adjust(left=.37,right=.97,top=.85,bottom=.2)
    fig.savefig(ROOT/'transfer-intervals.png',dpi=260,facecolor='white',bbox_inches='tight',pad_inches=.15)
    plt.close(fig)
if __name__=='__main__':main()

