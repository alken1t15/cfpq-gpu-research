# CFRA и реализация Хомки в CFG_bench

Проверяем производительность CFRA CUDA и реализации CFL_adv в CFG_bench на семи одинаковых CFPQ-запросах FLPQ_Data 6.0.0. CFG_bench запускается с полным набором оптимизаций `-efbl`. Версия CFG_bench — `ce2a4ca34fe3ed37ec0ba7037ebf251e5e84667a`, GraphBLAS — v10.5.1, LAGraph — `0242764eb854986dc8ea0228020f0df62e498bd7` из ветки `homka122/all_algorithms_benchmark`. [Исходники CFG_bench](https://github.com/homka122/CFG_bench)

## Входы и контроль ответа

Используем выборку из CUDA-отчёта. Конвертер повторно использует загрузчик CFRA и записывает индексированную метку в формате CFG_bench (`f_i_7` становится `f_i<TAB>7`). Грамматики копируются побайтно. SHA-256 подготовленных графов CFRA и грамматик совпали с записями CUDA-серии для 7 из 7 запросов; SHA-256 преобразованных файлов CFG_bench записаны отдельно.

Ожидаемые числа пар взяты из FLPQ_Data. Команда `-t` сверяет число пар с CSV и возвращает ошибку при несовпадении. `-t --compute-results` использует CFL_adv -efbl для вычисления эталона. Этот режим подходит для сверки другого решателя с CFL_adv, а контроль самого CFL_adv использует независимые опубликованные числа.

## Измерения

Для каждого запроса контроль, отдельный прогрев и пять измеряемых запусков процесса, лимит 900 секунд на запуск. Записываются полное время, внутреннее время CFG_bench, число пар и статус каждого запуска. Для межреализационного сравнения используем полное время процесса. Внутренние таймеры CFRA и CFG_bench охватывают разные участки кода. Сборки измеряются отдельными сериями. Подготовка файлов входа выполняется до запуска таймера.

```bash
python3 scripts/prepare-cfg-bench.py --out data/flpq-all/cfg-bench-inputs
python3 scripts/run-cfg-bench.py --repo /root/cfpq-homka/CFG_bench --inputs data/flpq-all/cfg-bench-inputs --out data/flpq-all/cfg-bench-runs
```

Для запуска нужна сборка CFG_bench с GraphBLAS и LAGraph в пути загрузки библиотек. Сырые файлы остаются в каталоге данных. Библиотеки собраны в локальном префиксе WSL. GraphBLAS compact собран с CPU JIT и OpenMP, CUDA-компилятор отсутствовал, CUDA JIT отключён. Для CFG_bench использован GCC 13 с флагами Makefile и добавленным -D_GNU_SOURCE: без него на этой системе strchrnul не объявлялась и штатный тест падал при чтении CSV. Штатная проверка и сокращённая выборка прошли 16/16. На момент записи серия из семи запросов выполняется.

Промежуточную или итоговую таблицу сравнения можно собрать из накопленных результатов:

```bash
python3 scripts/compare-cfg-bench.py --cfg-results data/flpq-all/cfg-bench-runs/results.jsonl --cfra-summary data/flpq-all/cuda-all-modes-summary.csv --out data/flpq-all/cfg-bench-comparison.csv
```
