"""Seal all public artifacts after all objective runs and both blind reviewer files have succeeded."""
from base31 import D,P,Path,sha,read,save
import subprocess,sys
def main():
    for f in ("forecast-seal.json","position-seal.json","score.json","attainable.json","blind-audit.json"):assert (D/f).is_file(),f
    if not (D/"reuse-audit.json").exists():subprocess.run([sys.executable,"-B","reuse31.py"],cwd=D,check=True)
    for script in ("review31.py","render31.py"):subprocess.run([sys.executable,"-B",script],cwd=D,check=True)
    doc=D/"REPORT_RU.md";s=read(D/"score.json");rr=read(D/"reuse-audit.json");cs=s["contrasts"];summary=s["summary"]
    co=rr["test_contrasts"];passed=all(cs["test/known/"+m+"/both_full"]["interval"][0]>0 for m in ("win_hybrid","turn_ensemble"))
    paragraph=(
        f"\n## Повторяющиеся сюжеты и устойчивость вывода\n\n"
        f"В 400 сценариях обнаружено {rr['distinct_normalized_questions']} разных нормализованных формулировок вопросов из 1200 и "
        f"{rr['distinct_normalized_fact_pairs']} различных текстовых пар старого и нового фактов. "
        f"Консервативная группировка связывает два сценария при точном совпадении хотя бы одного вопроса, совпадении обеих эталонных фраз или "
        f"сходстве полных троек вопросов по множеству 5-грамм не ниже 0,90. Тогда на 320 проверочных сценариев остаётся {rr['test_components']} компонент, "
        f"а {rr['test_cases_linked_to_dev']} проверочных сценариев связаны с разведочной панелью. Обучения по их результатам не было. "
        f"При пересэмплировании компонент альтернативные 97,5%-е интервалы в процентных пунктах для совместного выбора против гибридного окна и "
        f"против ансамбля составляют соответственно [{100*co['win_hybrid']['cluster_975'][0]:.2f} … {100*co['win_hybrid']['cluster_975'][1]:.2f}] и "
        f"[{100*co['turn_ensemble']['cluster_975'][0]:.2f} … {100*co['turn_ensemble']['cluster_975'][1]:.2f}].\n\n"
        f"По точному содержанию пользовательских реплик имеется {rr['distinct_session_bodies']} уникальных сессий из {rr['n_session_rows']}. "
        f"{rr['number_session_bodies_shared_across_cases']} разных текстов встречаются более чем в одном сценарии. Независимость от состава "
        f"других наборов памяти этот синтетический тест установить не позволяет.\n\n")
    if not passed:
        paragraph+=("Критерий перехода к дорогому эксперименту с ответами не достигнут. Предварительно требовался положительный прирост по доставке пары "
                    "на независимой панели против обоих основных контролей. Поэтому для этой версии политики завершены объективная оценка и две "
                    "семантические проверки одного набора из 24 примеров. Сравнивать её со штатным результатом CUPMem по конечным ответам оснований нет.\n")
    else:
        paragraph+=("Объективный этап прошёл оба заранее определённых порога. Для подтверждения качества ответа необходимо отдельное "
                    "сопоставление ридеров при одинаковой передаче и независимой оценке их ответов.\n")
    with doc.open("a",encoding="utf8") as fp:fp.write(paragraph)
    names={f.name:sha(f) for f in D.iterdir() if f.is_file() and f.name!="MANIFEST_SHA256.json"};save(D/"MANIFEST_SHA256.json",names)
    assert all(sha(D/n)==v for n,v in read(D/"MANIFEST_SHA256.json").items());print(len(names),sha(D/"MANIFEST_SHA256.json"),"gate",passed)
if __name__=="__main__":main()
