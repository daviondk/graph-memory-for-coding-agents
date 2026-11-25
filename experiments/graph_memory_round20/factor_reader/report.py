from pathlib import Path
import json
D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def fmt(x):return f"{100*x:.2f}".replace(".",",")
def effect(p):
    return f"{fmt(p['estimate'])} [{fmt(p['cluster_ci95'][0])}; {fmt(p['cluster_ci95'][1])}]"
def main():
    m=read(D/"prior.json")
    body=["# Полезность позиции в графе как априорный сигнал",
    "Сколько раз узел связан с аргументами, выходами инструментов и соседними фрагментами, известно до будущего вопроса. Оцениваем по исходному train, насколько такая позиция типична для нужного источника. Независимую калибровочную часть того же train используем, чтобы оценить полезность места в семантическом рейтинге Dense-FT. Во время чтения складываем два линейных скора. Все конечные решения выдаются в нативных родительских единицах; текст не дробится и состав доступных кандидатов совпадает с Dense-FT.",
    f"Структурная модель обучена на {m['train_trajectories']:,} траекториях и {m['train_questions']:,} вопросах с обоими классами. Все обучающие вопросы и исходные веса находятся в [файле модели](prior.json). Траектории обеих маленьких калибровочных выборок целиком исключены из обучения априорного компонента. Сам базовый текстовый энкодер был обучен на всём исходном train. Dev и test не обучают добавленные коэффициенты.",
    "При условной независимости ранга r и узловых признаков z внутри каждого класса Y справедливо log LR(r,z) = log LR(r) + log LR(z). При равных априорных шансах классов логит калиброванного классификатора оценивает log LR. Здесь это модельное обоснование, а не гарантированное свойство данных. Стоимость и глубина фрагмента могут коррелировать с семантическим рангом. В контрольном варианте исключаем признаки формы и используем только восемь направленных степеней. Для выдачи p-калибровка не нужна, важен порядок суммарного скора. [Протокол](PROTOCOL_RU.md)"]
    labels={"dense":"Исходный Dense-FT","rank":"Только калибровка ранга","shape":"Ранг + форма и роль","degree":"Ранг + типизированные степени","factor":"Ранг + общий структурный prior","joint":"Совместное обучение только на малой выборке","sham":"Prior переставлен внутри роли"}
    for co,title in (("hash64","Основная калибровка на 64 хеш-выбранных траекториях"),("availability","Калибровка по доступности кеша на 62 траекториях")):
        p=D/(co+"-results.json")
        if not p.exists():continue
        r=read(p);st=r["summary"];pairs=r["pairs"]
        body.extend(["## "+title,"| Вариант | Full Support, префикс | Coverage, префикс | Full Support, добор | Coverage, добор |\n|---|---:|---:|---:|---:|\n"+"\n".join(f"| {lab} | {fmt(st['prefix/'+k]['full_support'])}% | {fmt(st['prefix/'+k]['coverage'])}% | {fmt(st['skip/'+k]['full_support'])}% | {fmt(st['skip/'+k]['coverage'])}% |" for k,lab in labels.items()),
        f"Разность с тем же Dense-FT для первичного префикса, п.п. [95% ДИ]: полный вариант {effect(pairs['prefix/factor-dense']['differences']['full_support'])}, только степени {effect(pairs['prefix/degree-dense']['differences']['full_support'])}. Сопоставление парное по 2 000 вопросам, бутстреп по 1 207 траекториям. [Все эффекты]({co}-results.json) · [Поштучные исходы]({co}-outcomes.json.gz)"])
        ep=D/(co+"-extra-results.json")
        if ep.exists():
            ex=read(ep);v=ex["summary"];ci=ex["pairs"]["prefix/factor"]["differences"]["full_support"]
            body.append(f"Ещё 80 вопросов вне официальных dev500: Dense-FT {int(v['prefix/dense']['hits'])}/80, полный вариант {int(v['prefix/factor']['hits'])}/80, вариант по степеням {int(v['prefix/degree']['hits'])}/80. Разность первичной пары {effect(ci)} п.п. [Отложенный перенос]({ep.name})")
    body.extend(["## Что позволяют заключить контроли","Результат при перестановке prior оценивает пригодность чисел, прикреплённых к конкретным узлам. Этот контроль сохраняет роль, но может менять соответствие длины и числа связей. Разрушение самих рёбер с сохранением степеней исследует отдельный соседний эксперимент. Стоимость структурных признаков оплачивается один раз при построении графа истории; замеры сквозной задержки этим опытом не получены. [Контроль типизированной топологии](../typed_reader/REPORT_RU.md) · [Протокол дополнительной выборки](EXTERNAL_RU.md)"])
    if (D/"metrics-test.json").exists():body.append("[Все шесть столбцов таблицы ISETrace и Budget-AUC](METRICS_RU.md)")
    if (D/"channel_controls/test-results.json").exists():body.append("[Локальные и межсобытийные степени](channel_controls/REPORT_RU.md) · [Определения рёбер и авторский контроль](channel_controls/METHOD_RU.md)")
    if (D.parent/"untuned_holdout/test-strata.json").exists():body.append("[Совпадения обучающих полей и число событий](../untuned_holdout/STRATA_RU.md)")
    (D/"REPORT_RU.md").write_text("\n\n".join(body)+"\n",encoding="utf8")
if __name__=="__main__":main()
