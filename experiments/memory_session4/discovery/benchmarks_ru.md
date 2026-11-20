# Доступность официальных программных бенчмарков

Проверено 17 ноября 2026 года. HTTP-коды, revisions и полный перечень обнаруженных файлов записаны в access_receipts.json и access_receipts_extra.json. Проверка наличия файлов ещё не подтверждает исполнимость Docker-образов и совпадение результатов статьи.

## CompactionBench и APEC

Официальная страница Microsoft и preprint доступны. Страница не содержит ссылок на GitHub/Hugging Face артефакт. GitHub API exact-name search вернул t46/compactionbench и ayushnangia/CompactionBench. Их содержимое описывает другие наборы с таким названием. Hugging Face exact-name search нашёл compactionbench-lme-text-subset. Связь этих репозиториев с авторами Microsoft не установлена. Официальный release manifest, runner APEC и snapshot восьми release transitions в выполненном поиске не найден. Прямое воспроизведение paper-number сейчас требует авторского артефакта или полностью объявленной собственной реконструкции. [Microsoft](https://www.microsoft.com/en-us/research/publication/benchmarking-long-horizon-agent-context-compaction-with-compactionbench/)

## CoReMem и ChainSWE

В HTML CoReMem v1 отсутствует ссылка на авторский code/weights release. Публичный ChainSWE доступен на HF, commit dcaa484eca5b38caca71420712b1b194c1235d6e, файлы len_3, len_4, len_5, unique.parquet. Карточка сообщает 376 length-specific sequences и 213 unique sequences. Авторский SWE-Edit имеет evaluation/chainswe/evaluate.py, main.py, run_agent.py и test_reporter.py, tree cdf49074401c801606e2203d5b1a96823643e1e9. Наличие benchmark runner подтверждено. [ChainSWE](https://huggingface.co/datasets/C-lister/ChainSWE/tree/dcaa484eca5b38caca71420712b1b194c1235d6e), [runner](https://github.com/C-lister/SWE-Edit/tree/cdf49074401c801606e2203d5b1a96823643e1e9/evaluation/chainswe)

CoReMem описывает 100 chains с 52/48 split и 97/96 task boundaries. Эта конкретная выборка и CoReMem-trained weights в проверенных авторских ссылках не обнаружены. Общедоступный ChainSWE сам по себе не задаёт точную репликацию их теста. Сравнение на нашем опубликованном наборе возможно при запуске всех соперников заново и одинаковом унаследованном repository state. [Описание split](https://arxiv.org/html/2611.17316v1#A2)

## REM и SWE Context Bench

REM HTML v1 не содержит ссылок на авторский implementation release. Его underlying benchmark реально опубликован. HF jiayuanz3/SWEContextBench имеет commit 12c65bd15e2559bc808065565e941ee7bbbd008f и пять parquet с experience, related, lite и relationship. GitHub jiayuanz3/SWEContextBench tree 12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b содержит cases, evaluation.sh и swebench_memory/harness/run_evaluation.py. Карточка ссылается на Docker images. [Данные](https://huggingface.co/datasets/jiayuanz3/SWEContextBench/tree/12c65bd15e2559bc808065565e941ee7bbbd008f), [harness](https://github.com/jiayuanz3/SWEContextBench/tree/12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b)

Есть расхождение заявленных объёмов между версиями статьи и текущей карточкой. Для exact-paper comparison следует зафиксировать 99 related task IDs, исходный experience pool, версию мини-агента и его модели. Официальный benchmark является реальным кандидатом для нового shared-harness исследования, а REM-policy придётся реализовать по статье с явным отчётом о fidelity. [REM](https://arxiv.org/html/2610.27377v1), [карточка](https://huggingface.co/datasets/jiayuanz3/SWEContextBench/blob/12c65bd15e2559bc808065565e941ee7bbbd008f/README.md)

## Continual SWE

Точное название Continual-SWE не удалось связать с отдельной первичной публикацией и официальным артефактом. HF API exact-name search дал пустой ответ. GitHub exact-name search дал два посторонних по описанию проекта. Поиск в вебе выводил SWE-Bench-CL и Can Coding Agents Sustain Continual Evolution without Forgetting. Эти работы имеют самостоятельные названия, данные и постановки.

SWE-Bench-CL действительно опубликован с авторским agents-never-forget, tree 74a38a90baace25635f3827ee2f98caff24b3768. Найдены eval_v1, eval_v2_agent, eval_v3_swe-agent и curriculum artifacts. Проверка наличия не устанавливает соответствие всех этих эволюционирующих runners финальному протоколу. [Статья](https://arxiv.org/abs/2507.00014), [репозиторий](https://github.com/thomasjoshi/agents-never-forget/tree/74a38a90baace25635f3827ee2f98caff24b3768)

Для continual harness evolution авторы прямо ссылаются на THU-Agent/continual-harness-evolution. Проверен tree bb84e4a68fe0b51d7420ef4413c5061f4f074c04, 1 600 файлов, включая адаптеры и evolution scripts. Работа исследует перенос между типами coding tasks. [Публикация](https://arxiv.org/html/2611.03219v1), [артефакт](https://github.com/THU-Agent/continual-harness-evolution/tree/bb84e4a68fe0b51d7420ef4413c5061f4f074c04)

## Практическая последовательность сравнения

Первым воспроизводимым направлением выбрать SWE-ContextBench Lite или exact опубликованный ChainSWE subset. При каждом сравнении фиксировать actor version, одинаковый harness, task IDs, inherited tree, memory-writing input, контекстный бюджет, seeds и все writer/reader costs. Отдельно воспроизвести no-memory и авторский формат памяти на этом наборе. Размерностные результаты простого CPU replay служат проверкой механизма перед такими запусками.

