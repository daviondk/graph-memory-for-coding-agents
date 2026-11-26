"""Describe train-estimated coefficients and ungraded probability similarities. Do not open outcomes."""
from train_model import D,BASE,read,dump
import numpy as np
from scipy.stats import spearmanr
def main():
    p=read(D/'probabilities.json.gz');part=read(BASE/'panels.json');models=read(D/'models.json');full=read(BASE/'model.json')['candidate']
    doc=['log_chars','log_identifiers','log_lines','test_path','path_depth','docs_path','config_extension','def_count','class_count','assert_count','raise_count','return_count','import_count','if_count','test_identifiers','self_count','except_count','arrow_count','comment_count','type_count']
    overlap=[f'{q}_{s}_{f}' for q in ['query','need','subgoal','issue'] for s in ['content','path','declarations','calls'] for f in ['idf_overlap','query_coverage','doc_coverage']]
    qc=['behavior','location','api','verification','interaction','history','implementation','failure','configuration','docs','reproduction','file']
    names=doc+overlap+['full_path_literal','filename_literal']+[f'query_{q}' for q in qc]+[f'query_{q}_times_test' for q in qc]+[f'query_{q}_times_n_declarations' for q in qc]+['log_bm25','inv_sqrt_bm25_rank','normalized_bm25']
    assert len(names)==109
    d={}
    for k,coef,cols in [('full',full['beta'][-1],range(109))]+[(k,v['beta'][0],models['schema'][k]) for k,v in models['models'].items()]:
        pairs=[(names[j],float(v)) for j,v in zip(cols,coef,strict=True)]
        d[k]=sorted(pairs,key=lambda z:-abs(z[1]))
    split={}
    for splitname in ['dev','outside']:
        out={}
        for a,b in [('full','document'),('full','match'),('match','document')]:
            rr=[];intersection=[]
            for q in part[splitname]:
                x=np.asarray(p[q][a]);y=np.asarray(p[q][b]);r=spearmanr(x,y).statistic
                if np.isfinite(r):rr.append(float(r))
                intersection.append(len(set(np.argsort(-x,kind='stable')[:8])&set(np.argsort(-y,kind='stable')[:8])))
            out[a+' vs '+b]=dict(median_spearman=float(np.median(rr)),mean_spearman=float(np.mean(rr)),defined=len(rr),mean_top8_overlap=float(np.mean(intersection)))
        split[splitname]=out
    dump('model-audit.json',dict(coefficient_scale='one training standard deviation, multivariate conditional association',standardized_coefficients=d,ungraded_probability_similarities=split))
    print('Verified feature index names and ungraded rank similarities.')
if __name__=='__main__':main()

