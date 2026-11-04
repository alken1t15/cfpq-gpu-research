# Воспроизведённые проблемы и статус

| ID | Наблюдение | Свидетельство | Статус |
|---|---|---|---|
| CFRA-1 | `_i` исчезает при раскрытии имени; реальный luindex выдаёт7472 вместо9677 | experiments/2026-11-03-edge-cases, 2026-11-03-java | Локальная правка в ветке CFRA; регрессии пройдены |
| CUDA-1 | A\empty даёт empty вместо A | GPU setup primitive-gpu.json: A={(0,1)}, B=empty | Исправлено в отдельной trial-библиотеке; atom incremental0→6 |
| CUDA-2 | MxM теряет пары даже с отдельным выходом | GPU setup primitive-gpu.json, последний пример3×3:5 ожидаемых пар,3 фактических | Корневая причина ещё не изолирована; проверить nsparse count/fill |
| CUDA-3 | MxM при результате=левому/правому входу отличается от CPU | GPU setup matrix-all-results.json и matrix-test.log | Воспроизведено; уточнить контракт alias отдельно от nonalias бага |

GPU illegal memory access в отдельных CFPQ-запусках сохранён в stderr; не считать его отдельной установленной корневой причиной без изоляции. GPU correctness gate не пройден.

CPU fast path пустых accumulated unions — оптимизация, а не исправление неверного CPU-ответа. На incremental/luindex измерено1.606×; расширенная correctness-серия34 совпадения/2 таймаута. Оформление — experiments/2026-11-03-empty-union-trial и 2026-11-03-trial-catalog.
