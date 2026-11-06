# Explicit row mask и отдельная проверка alias

Дата:2026-11-06. Базовый коммит0154064, production cuBool fork37ccfd8. Новая ветка research/gpu-mxm-fixed-mask. Все изменения генерируются отдельно; src/cfra не меняется. CUDA12.4, RTX3060Laptop8.6, Release, CUDA-only library из build/gpu-cubool-pr19, CPU fallback OFF.

## Изменение 1: маска редукции

В count_nz_pwarp_row четыре соседних потока обрабатывают одну строку. Их состав задан индексами, а не текущей сходимостью. Новая маска имеет четыре бита, начиная с номера первой lane строки; shuffle использует width=pwarp. Добавлена compile-time проверка размера группы:степень двойки от1до32. Все потоки одной строки либо выходят по rid>=n_rows, либо доходят до редукции; поэтому участники маски существуют и вызывают shuffle с одинаковой маской. Разные строки используют непересекающиеся маски. Текущий вызов pwarp=4, block256, одномерный grid/block.

Это заменяет экспериментальную раннюю __activemask из предыдущей сессии. Одна лишь предварительная __syncwarp не гарантирует сохранение сходимости до последующей инструкции:это отдельно объясняет NVIDIA. См.docs/CUDA_AUDIT.md.

Исходный header не изменён; новый header в build/gpu-fixed-mask. Пересобран только multiply.cu.o с этим include, остальные объекты прежние. Baseline library SHA256 до/после проверен. Команды:build-commands.json, хеши:manifest.json, переносимый кандидат:fixed-mask.patch. Добавлен -lineinfo для возможной инструментальной диагностики; performance не измеряется.

## Проверки изменения 1

69 входов ×accumulate ON/OFF=138 сравнений полных множеств и числа nvals. Размеры строк включают1,2,3,7,8,9,31,32,33,63,64,65,127,128,129. Число столбцов и плотных выходных строк проверено вокруг32,64,128,256,512,1024,2048,4096 (до4097 включительно), плюс24seeded random прямоугольных входа. Seed20261106. Fixtures генерируются скриптом, отдельные матричные датасеты не требуются. Тесты distinct-output; источник и цель не совпадают.

- Baseline cuBool с PR19:88/138, exit1 из-за неверных ответов.
- Explicit-mask trial:138/138, exit0.
- Прежний3×3набор с alias:622/864, оставшиеся242fail толькоnonaccumulate alias.

Первый прогон138 сравнивал множества, затем добавлена проверка nvals==|expected| для обнаружения дубликатов выходных пар. После изменения oracle обе библиотеки перепроверены, итоговые результаты выше относятся к усиленной проверке.

## Изменение 2: отдельный alias trial

В копии cuda_matrix_multiply.cu добавлено:если result совпадает с любым входом и accumulate=false, сначала вычислить ответ во временную CudaMatrix, затем перенести данные в result. Все входы живут до завершения вычисления, рекурсия заканчивается на distinct-output. Изменение накладывается только поверх explicit-mask trial; это отдельная библиотека build/gpu-alias-trial. Файлы:alias.patch,alias-build-commands.json,alias-manifest.json.

- Расширенный набор:864/864, включая left/right/both alias,accumulate ON/OFF, deferred SetElement и Build.
- Малые24примитива:24/24.

Это проверка поведения, а не окончательное толкование API-контракта: C-заголовок явного обещания/запрета nonaccumulate alias не содержит, Python mxm показывает out=a в accumulate=True. Перед интеграцией согласовать с участниками. Предыдущее поведение CPU отличается от GPU.

## Инструментальная проверка

Установлен cuda-sanitizer-12-4 из уже подключённого NVIDIA repo. На baseline/count-probe attempted memcheck и synccheck. Оба НЕ инициализировали WDDM debugger interface и сообщили Device not supported. GPU memory/race/sync проверка фактически не выполнена. ERROR SUMMARY2 относится к двум ошибкам запуска инструмента, не к двум найденным дефектам ядра. Windows-настройки отладки не менялись. install log/count-*-logs сохранены.

## Воспроизведение

```bash
python3 /mnt/d/semen_task_avtomat/scripts/build-gpu-fixed-mask.py
python3 /mnt/d/semen_task_avtomat/scripts/check-gpu-mxm-boundaries.py /mnt/d/semen_task_avtomat/build/gpu-fixed-mask/libcubool.so /mnt/d/semen_task_avtomat/experiments/2026-11-06-fixed-mask/boundaries-trial.json
python3 /mnt/d/semen_task_avtomat/scripts/build-gpu-fixed-mask.py --alias
python3 /mnt/d/semen_task_avtomat/scripts/check-cubool-mxm-pairs.py /mnt/d/semen_task_avtomat/build/gpu-alias-trial/libcubool.so --gpu --collect-failures
```

Baseline boundaries запускается той же командой с library build/gpu-cubool-pr19/cuBool/cubool/libcubool.so. Остальные проверки:probe-matrix-primitives.py с выбранной library и --gpu. Проверки проводились параллельно с отдельной длительной luindex-пробой; это допустимо для проверки результатов, но времена не являются benchmark.

Ни результат864/864 на3×3, ни138/138 на выбранных размерах не доказывают полную корректность GPU. Sanitizer недоступен, прочие операции/размеры требуют исследования. Статические риски вfill_nz иcount_nz_block_row отдельно описаны вCUDA_AUDIT; неверный ответ из-за них пока не воспроизведён. Исследование не устанавливает эксплуатируемых уязвимостей безопасности.


## Ограниченная попытка luindex

Запущен incremental с explicit-mask library и GNU timeout180s. Ответ в stdout не получен. При передаче shell-команды через Windows/WSL переменные оболочки были изменены; запись exit-status оказалась пустой, внешняя оболочка завершилась1 с numeric argument required. Надёжного кода дочернего процесса нет. Попытка считается inconclusive_wrapper_error, не подтверждённым таймаутом/зависанием. Будущие длительные запуски — через Python subprocess.run(timeout=...) с JSON. Данные:luindex-attempt.json,stdout,stderr,exit. Старую подтверждённую30с серию предыдущего эксперимента это не меняет.

## Проверка записи за логической границей

probe-gpu-fill-guard.py собрал и запустил отдельные count+fill CUDA-ядра на прежнем3×3контрпримере. Физически выделено8элементов; логический размер берётся из prefix sum результатов count, как в fill_nz_functor. Все8элементов сначала заполнены sentinel777. Это безопасный стенд, где запас физической памяти позволяет наблюдать выход за расчётную границу, не повреждая чужие выделения.

Baseline:логический размер3, fill пишет5значений и меняет2элемента защитной области —5/5повторов. Explicit mask:логический размер5, fill пишет теже5значений, защитная область неизменна —5/5повторов. Артефакты:fill-guard.cu,fill-guard-results.json,compile-команды вJSON.

В реальном fill_nz.h values_count=row_idx.back() задаёт размер выходного vector, то есть3вместо5наэтом пути. Следовательно, подтверждённая ошибка count имеет также последствие для границ записи fill. Это не просто неверное число пар. Проба намеренно использует физический запас; не утверждаем, что ComputeSanitizer обнаружил нарушение, поскольку он не запустился. Причина всех прежних illegal memory access этим экспериментом не доказана; эксплуатируемость как уязвимость безопасности не исследована.

```bash
python3 /mnt/d/semen_task_avtomat/scripts/probe-gpu-fill-guard.py
```
