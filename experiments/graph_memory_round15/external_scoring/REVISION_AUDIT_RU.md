# Проверка исходной ревизии IssueLoc-Bench

Для 198 архивных задач с теми же репозиторием и номером PR **45 исходных коммитов совпали с первым родителем коммита метки IssueLoc**. Во всех 198 случаях архивный SHA отличался от самого поля `labels.commit_sha`. Различие с этим полем само по себе не доказывает несовпадения деревьев, предъявляемых системам поиска.

Официальный сборщик IssueLoc загружает объект `commit_sha` с глубиной 2 и пытается вычислить `git rev-parse <commit_sha>^`. В Git запись с `^` без номера выбирает первого родителя. При успешном разрешении авторы используют его как `tree_source_sha` для снимка, а при отсутствии родителя используют сам коммит. В метаданных сборщика предусмотрены отдельные поля исходного коммита метки, родителя и источника дерева. Сверка ниже проверяет идентичность коммитов по этому правилу. Индивидуальные опубликованные файловые снимки целиком побайтно не сравнивались. Статус head или merge конкретного PR из одного имени поля не выводим. [Официальный сборщик IssueLoc, разрешение родителя](https://github.com/mohammad-nour-alawad/IssueLoc-bench/blob/bd546b8ec1067eb4690cc0677a05320e88e35ff4/localization_bench/snapshot_builders/build_issueloc_bench_dataset.py#L153-L162) · [Выбор источника дерева](https://github.com/mohammad-nour-alawad/IssueLoc-bench/blob/bd546b8ec1067eb4690cc0677a05320e88e35ff4/localization_bench/snapshot_builders/build_issueloc_bench_dataset.py#L426-L445) · [Метки рассматриваемого сплита](https://github.com/mohammad-nour-alawad/IssueLoc-bench/blob/bd546b8ec1067eb4690cc0677a05320e88e35ff4/issueloc_bench_manifest/labels/transformed_swe_bench.jsonl)

| Репозиторий | Совпали repo и PR | База равна первому родителю | База равна другому родителю |
|---|---:|---:|---:|
| astropy/astropy | 16 | 6 | 0 |
| matplotlib/matplotlib | 29 | 6 | 0 |
| mwaskom/seaborn | 2 | 1 | 0 |
| pydata/xarray | 17 | 0 | 7 |
| pylint-dev/pylint | 4 | 0 | 2 |
| pytest-dev/pytest | 13 | 5 | 0 |
| scikit-learn/scikit-learn | 26 | 0 | 5 |
| sphinx-doc/sphinx | 38 | 15 | 7 |
| sympy/sympy | 53 | 12 | 6 |
| **Всего** | **198** | **45** | **27** |

У оставшихся 126 задач с базой не совпал ни один непосредственный родитель. Более дальнее родство коммитов и возможность идентичных деревьев при разных SHA здесь не устанавливались. Девять пакетных запросов Git protocol v2 к публичным репозиториям запросили только объекты коммитов (`deepen 1`, `filter tree:0`). Для каждого возвращённого объекта проверен Git SHA-1 по содержимому и извлечены упорядоченные поля parent из заголовка. Все 198 объектов получены. SHA256 канонически отсортированного массива из четырёх полей `[instance_id, archive_base, labels_commit, ordered_parents]` равен `0f86cb3c79c50fffb678bf6596fbe5494971e3ff6e97943065c612f3e699e004` (JSON без пробелов между элементами). Пример совпадения — `mwaskom__seaborn-3069`, чей первый родитель равен архивной базе `54cab15bdacfaa05a88fbc5502a5b322d99f148e`. [Проверяемый коммит этой задачи](https://github.com/mwaskom/seaborn/commit/e99a1e4b83f7e076b54942e5f8fde2364f2cd2e4)

## Метрики на 45 совпавших ревизиях

Знаменатель включает 24 задачи с доступным архивным чтением и 21 задачу с пустой памятью. Ранжирования зафиксированы ранее. Оценка считает пути файлов на заведомо ограниченном архивном префиксе.

| Метод | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Первый просмотренный файл | 11/45 | 16/45 | 0,3000 |
| Последний просмотренный файл | 13/45 | 16/45 | 0,3185 |
| Число повторных просмотров | 13/45 | 16/45 | 0,3185 |
| Повторяемость и связи по идентификаторам | 14/45 | 16/45 | 0,3333 |

Граф дал одно дополнительное попадание на первом месте относительно давности. При трёх слотах все методы покрыли одинаковое число задач. Внешняя шкала метрик здесь воспроизведена на производной панели из 45 корректно сопоставленных ревизий. Отличия бюджета и доступных действий ограничивают сравнение с системами, которые самостоятельно исследуют полный репозиторий.

## Идентификаторы совпавших ревизий

```text
astropy__astropy-13977
astropy__astropy-14096
astropy__astropy-14309
astropy__astropy-14539
astropy__astropy-7166
astropy__astropy-7671
matplotlib__matplotlib-13989
matplotlib__matplotlib-20676
matplotlib__matplotlib-20826
matplotlib__matplotlib-22871
matplotlib__matplotlib-23476
matplotlib__matplotlib-26208
mwaskom__seaborn-3069
pytest-dev__pytest-10081
pytest-dev__pytest-5809
pytest-dev__pytest-7236
pytest-dev__pytest-7571
pytest-dev__pytest-7982
sphinx-doc__sphinx-10435
sphinx-doc__sphinx-7454
sphinx-doc__sphinx-7590
sphinx-doc__sphinx-7748
sphinx-doc__sphinx-7757
sphinx-doc__sphinx-7889
sphinx-doc__sphinx-7985
sphinx-doc__sphinx-8035
sphinx-doc__sphinx-8548
sphinx-doc__sphinx-8595
sphinx-doc__sphinx-8721
sphinx-doc__sphinx-9258
sphinx-doc__sphinx-9281
sphinx-doc__sphinx-9367
sphinx-doc__sphinx-9591
sympy__sympy-12096
sympy__sympy-12419
sympy__sympy-17655
sympy__sympy-18763
sympy__sympy-19637
sympy__sympy-21847
sympy__sympy-23262
sympy__sympy-23413
sympy__sympy-23950
sympy__sympy-24443
sympy__sympy-24539
sympy__sympy-24661
```
