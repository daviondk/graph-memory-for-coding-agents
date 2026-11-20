from collections import Counter
from util import *
def main():
    triallock=read(ROOT/'decision_lock.json')
    jr=read(ROOT/'judge_lock.json');q=read(ROOT/'results.json')
    assert len(triallock['trials'])==120 and (ROOT/'offline_actor_verified.json').exists()
    for name,h in jr.items():check(ROOT/name,h)
    verify=read(ROOT/'offline_actor_verified.json')
    workspace=read(ROOT/'workspace_audit.json.gz')
    shown=Counter(x['arms']['git']['docs_edited_before_first_request'] for x in workspace.values())
    corpus=read(ROOT/'published_settings.json')
    env=read(ROOT/'input_lock.json');rx=q['encoding_recovery'];costs=q['actor_extra_audit']
    texts=['# Журнал локального сравнения','',
        f"Протокол, порядок вопросов, код, данные benchmark и родительские источники зарегистрированы {env['created']}. Обновлённые результаты агента до регистрации не оценивались.",
        'Для проверки соответствия названий стратегиям прочитаны README.md, eval_pioneer.py и реальные поля всех 15 авторских архивов. На всех трёх опубликованных моделях Oracle имел policy=raw, apply_a_side_mutations=false и race_candidate_path=null. Остальные четыре конфигурации содержали патчи. Контрольные суммы находятся в published_settings.json.',
        f"Первая попытка столкнулась с кодировкой текущего процесса Windows. После включения UTF-8 повторено {rx['completed_before_restart']} ранее завершённых траекторий. Полностью совпало {rx['identical_full_trials_after_restart']}; первоначальные квитанции находятся в recovery_default_encoding, а исходный код эксперимента и запросы не редактировались.",
        f"До формирования слепых вердиктов зафиксировано {len(triallock['trials'])} новых траекторий в {triallock['created']}. Накоплено {costs['logical_requests']} логических запросов, из них {costs['distinct_keys']} различных; {costs['keys_reused_from_original']} различных полных тел уже имели родительскую нативную квитанцию. Здесь верифицируется точный текст с историей и инструментами, одним эмбеддингом или вопросом совпадения не определяются.",
        'Слепой судья использует только question/gold/prediction в исходном шаблоне. Метки политик остаются в отдельной таблице назначений; совпадающий промпт имеет общий результат. Вторичный анализ пропусков зарегистрирован в missingness_lock.json до оценивания новых 120 ответов.',
        f"В чистых временных директориях повторено {verify['regenerated_trajectories']} tool-loop запусков по оригинальным нативным ответам. Полностью совпали все параметры запросов, инструменты и их наблюдения, остановки и ответы. Контроль одинаковых исходных корпусов до A-сайд модификации записан в workspace_audit.json.gz; распределение числа изменённых до первого обращения документов среди вопросов составляет {dict(shown)}. Oracle в каждом случае сохранил неизменные начальные файлы.",
        'Доля, доступная на сорока вопросах, проверяется автономным verify.py. Полная проверка дополнительно требует закреплённого исходного benchmark и родительских нативных квитанций. Модель, seed, контекст, лимит действий, вопросы и инструменты указаны в исходном протоколе. Работа не отправлялась внешнему судье.']
    if (ROOT/'results_with_highlight.json').exists():texts.append('После отдельной фиксации результатов подсветки добавлена таблица с семью локальными режимами. Пять опубликованных конфигураций по-прежнему составляют первичную группу сравнения.')
    (ROOT/'RESEARCH_LOG.md').write_text('\n\n'.join(texts)+'\n',encoding='utf8')
    paths=[p for p in ROOT.rglob('*') if p.is_file() and not ({'work','__pycache__'} & set(p.relative_to(ROOT).parts)) and p.name not in ('manifest.json','finish.log')]
    manifest={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in paths}
    save(ROOT/'manifest.json',{'hashes':manifest,'omitted':'derived workspaces and running coordinator log'})
    for n,h in manifest.items():check(ROOT/n,h)
    print('verified',len(manifest),'immutable local artifacts')
if __name__=='__main__':main()

