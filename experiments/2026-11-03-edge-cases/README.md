# Исправление раскрытия индексированных шаблонов

Дата: 2026-11-03. Статус: воспроизведено и локально исправлено.
Основа: CFRA `3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1`, cuBool `1d4e760bc0d76906b81c70c505d6b29b4d9d3f11`.
Ветка `fix/indexed-template-expansion`, изменения пока не закоммичены и не опубликованы. Среда CPU Release GCC13.4/WSL из предыдущего smoke-test. GPU не проверялся.

## Вопрос и воспроизведение

Сохраняет ли шаблонная запись грамматики ответ явно раскрытой версии?
Граф: `0 1 open_i_3`, `1 2 close_i_3`.
Грамматика: `S open_i close_i`, старт S. Язык — open_i_k close_i_k с одним и тем же индексом k. Единственная ожидаемая пара (0,2).
Явная грамматика `S open_i_3 close_i_3` даёт 1, шаблонная в исходном коде даёт 0 для всех трёх алгоритмов.

```powershell
wsl -d Ubuntu -- python3 /mnt/d/semen_task_avtomat/scripts/check-edge-cases.py
```

Восемь малых случаев, по три алгоритма: chain, epsilon_chain, epsilon_product, duplicates_loop, absent_terminal, indexed_explicit, indexed_template, indexed_two_values. Ожидаемые пары заданы вручную в скрипте и сохранены вместе с входами. Первичный код завершения 1, после исправления 0.

## Причина и исправление

`grammar.cpp` находит индекс по префиксу `<symbol>_`, но instantiate удалял последнюю букву `i`: `open_i` → `open_3`. Фактическая метка `open_i_3` не совпадала. Исправление сохраняет исходный символ и добавляет `_` и индекс. Формат подтверждён README (`load_i_3`) и штатным `test_data/indexed_an_ab/grammar.cnf.expanded`, где используются a_i_0 и Sb_i_0.

Изменён только механизм формирования имени в парсере. Матричные алгоритмы не менялись. В `ci/test.sh` добавлены три проверки indexed_pair; минимальные graph.txt и grammar.cnf добавлены в `src/cfra/test_data/indexed_pair/`.

## Проверки до и после

- До: 18/24 прошли, 6/24 не прошли (два шаблонных случая × три алгоритма). [baseline-results.json](baseline-results.json).
- После: 24/24 прошли. [results.json](results.json).
- Тестовый скрипт проекта после добавления регрессии: 9/9. [tests-direct.log](tests-direct.log).
- Внешние atom/bzip: 12/12 после исправления; [catalog-before.json](catalog-before.json), [catalog-after.json](catalog-after.json).
- `git diff --check`: успешно. Сборка после изменения: [rebuild.log](rebuild.log).

Повторная CPU-сборка — `wsl -d Ubuntu -- bash /mnt/d/semen_task_avtomat/scripts/wsl-cpu-smoke.sh`. Прямой запуск тестов без повторной конфигурации: из WSL в src/cfra выполнить `bash <(sed -e 's/\r$//' -e 's|^CFRA=./build/cfra$|CFRA=./build-cpu-gcc13/cfra|' ci/test.sh)`.

Патч отслеживаемых файлов: [cfra.patch](cfra.patch); новые fixture-файлы лежат в клоне. Внешний скрипт с полными восемью входами сохранён в scripts/check-edge-cases.py, а фактические входы — в подпапках этого эксперимента.

## Ограничения

Сравниваются количества, CLI не выдаёт множества пар. Это correctness baseline и исправление парсера, не оптимизация алгоритма. Performance baseline не снимался: ускорение не заявляется. Нужна последующая проверка на реальных индексированных грамматиках из каталога; её не заменяют эти малые примеры. Пустой граф и формат представления изолированных вершин остаются отдельными вопросами.
