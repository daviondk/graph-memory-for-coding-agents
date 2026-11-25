"""Write the human-facing report from sealed outcomes and freeze the portable files."""
from pathlib import Path
import hashlib
import json

D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(x,places=2):return f"{x:.{places}f}".replace(".",",")
def main():
    r=json.loads((D/"results.json").read_bytes())
    rows=["# Чтение графовой памяти при бюджете 2 048 токенов","",
          "Поверх R-GCN с удалённым типом рёбер content.next сравнили две политики чтения. Для обоих вариантов использовали один порядок источников. Итоговый контекст повторно токенизировали и учитывали только действительно выданные символы.","",
          "| Политика | Полный источник | FS, % | Coverage, % | Density, % | F1, % | Среднее число токенов | Обрезано выдач |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for a,label in (("skip","Целые PU по рангу с пропуском неумещающихся"),("ratio","Первые два PU и короткие интервалы по p/c")):
        v=r["summary"][a];vs=" | ".join(fmt(100*v[k]) for k in ("full_support","coverage","density","f1"))
        rows.append(f"| {label} | {int(v['hits'])} / 2 000 | {vs} | {fmt(v['tokens'],1)} | {v['trims']} |")
    rows+=["","Парная разность между p/c и целыми PU измерена на 2 000 вопросах из 1 207 траекторий. В скобках приведены 95% доверительные интервалы по 10 000 повторов кластерного bootstrap.","",
           "| Показатель | Разность в п.п. | 95% ДИ в п.п. |","|---|---:|---:|"]
    for k,label in (("full_support","Full Support@2048"),("coverage","Coverage@2048"),("density","Density@2048"),("f1","F1@2048")):
        v=r["pairs"]["differences"][k];lo,hi=v["cluster_ci95"]
        rows.append(f"| {label} | {fmt(100*v['estimate'])} | {fmt(100*lo)} … {fmt(100*hi)} |")
    rows+=["",f"После перехода на p/c выдача стала полностью покрывать эталон в {r['wins']} случаях и потеряла часть источника в {r['losses']}. Максимальная длина составила 2 048 токенов. Ни одно обрезание при повторной токенизации не изменило Full Support.",
           "","Модель читателя обучена на исходном train и перенесена с прежними весами. Протокол пары зафиксирован до появления первого шарда нового ранжировщика. Тот же механизм давал +2,00 п.п. Full Support поверх Dense-FT и +1,85 п.п. поверх обычного R-GCN. Во всех трёх проверках использованы одинаковые тестовые вопросы, seed 13 и локальная процедура выбора графовой модели на 500 dev. Остаются открытыми величина эффекта при других seed и влияние чтения на успешность задач агента.",
           "","[Исходный протокол](PROTOCOL_RU.md) · [Все парные результаты](results.json) · [Индивидуальные оценки](strict-metrics.json.gz) · [Проверка на обычном R-GCN и Dense](../../graph_memory_round20/fine_train/REPORT_RU.md)"]
    (D/"REPORT_RU.md").write_text("\n".join(rows)+"\n",encoding="utf8")
    manifest=D/"MANIFEST_SHA256.json"
    files={p.name:sha(p) for p in sorted(D.iterdir()) if p.is_file() and p!=manifest}
    manifest.write_text(json.dumps({"files":files,"count":len(files),"bytes":sum((D/name).stat().st_size for name in files)},sort_keys=True,indent=2)+"\n",encoding="utf8")
    assert all(sha(D/n)==h for n,h in files.items())
    print(len(files),"files manifested;",sha(manifest))
if __name__=="__main__":main()

