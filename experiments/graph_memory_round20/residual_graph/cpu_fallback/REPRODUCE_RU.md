# Резервные CPU-панели

Обе панели используют R20/residual_graph/protocol-lock.json и замороженный PU Dense-FT из R19/trained_rank. Точное разбиение и критерии указаны в PROTOCOL_RU.md и cohorts.json. Исходный complete-train эксперимент имеет собственные результаты. Проверка любой готовой панели выполняется из cpu_fallback:

    python -B verify_panel.py availability
    python -B verify_panel.py hash64

Проверка использует только стандартную библиотеку Python. Независимая арифметика, исходные разметки и координаты вызовов test и dev включены в данный каталог. Полная офлайн-проверка двух панелей и интервенции: python -B verify_bundle.py. Заново считаются точное покрытие, плотность, F1, количество выбранных узлов и WordPiece для всех 15 000 индивидуальных исходов на каждую панель. Проверяется точное применение всех трёх правил на test и dev. SHA рангов dev и test указаны вместе в manifest каждой панели и в forecast-seal.json.

Восстановив проект и данные из родительской инструкции, выполнить в закреплённой среде PyTorch 2.6.0:

    python -B fallback.py plan
    python -B fallback.py encode availability
    python -B fallback.py train availability
    python -B read.py rank availability
    python -B read.py score availability
    python -B finish_panel.py availability

Повторить четыре вычислительные стадии и finish_panel для hash64. Для исходной availability-когорты использовать зафиксированную outage-train-availability.json.gz, иначе новые закэшированные векторы изменят смысл панели. Формирование полной независимой от кэша hash64 использует только ID train-траекторий. Для повторения с нуля разрешено закодировать все входы каждой модели в FP32. Ранее построенные FP32-векторы на RTX 3090 и новые CPU-векторы могут отличаться в младших разрядах. По журналу cpu-encoding.json можно восстановить стоимость этого конкретного запуска.

Состояния missing/completed после сбоя хранятся в ../gpu-outage.json, ../outage-coverage.json и ../outage-train-availability.json.gz; ошибки CUDA и CPU-счётчики лежат отдельно в рабочем RUN/logs. В резервном опыте сохранена авторская функция train_provenance_graph_retriever и исходное правило dev selection со включённой эпохой 0. Модели переобучены только на исходных train-примерах выбранных панелей. Упорядоченные тестовые и dev-прогнозы формируются при одинаковых 768-мерных признаках, размере пула и входном cosine. Во время инференса производится побитовое сравнение выхода исходного нулевого residual со всеми seed-логитами.

