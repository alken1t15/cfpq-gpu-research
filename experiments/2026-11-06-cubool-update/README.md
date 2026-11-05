# Обновление cuBool из PR19

Дата: 2026-11-06. Перенос исходников: коммит a7c19b6. Baseline cuBool: 1d4e760bc0d76906b81c70c505d6b29b4d9d3f11. Обновлённая версия: fork vano105/cuBool, master 37ccfd818f3bc9c5cb6483a2e76fc73ee93a01f3, https://github.com/SparseLinearAlgebra/cuBool/pull/19 (на момент проверки не влит).

Это чужое существующее исправление GPU-разности, а не новый авторский вклад. Отличия: обработка пустого источника/маски в CUDA eWiseMultInverted, три регрессии, включение тестового бинарника в shell runner. Собственные опытные оптимизации не интегрированы.

Новая сборка не затрагивает baseline-каталоги. Команда в WSL (параметры идентичны фактическому прямому вызову CMake в build.log):

```bash
CFRA_BUILD_DIR=/mnt/d/semen_task_avtomat/build/gpu-cubool-pr19 bash /mnt/d/semen_task_avtomat/scripts/build-wsl-gpu.sh
python3 /mnt/d/semen_task_avtomat/scripts/probe-matrix-primitives.py /mnt/d/semen_task_avtomat/build/gpu-cubool-pr19/cuBool/cubool/libcubool.so --gpu
```

Сборка: Release, gcc/g++13, nvcc12.4, CUDA host gcc11, arch86, CUDA ON, CPU fallback OFF, upstream тесты OFF. Вместо полного набора upstream выполнена целевая проверка полных множеств пар 24 маленьких примитивных случаев. Её фактический результат записывается после сборки. Повторный benchmark не выполняется.

## Результат

CMake configure/build завершены с кодом0, GPU-only executable собран. `wsl -d Ubuntu -- python3 /mnt/d/semen_task_avtomat/scripts/check-cubool-update.py` завершён с кодом1:23/24 примитивов,3/3 CFPQ atom. Код1 означает сохранение известного дефекта MxM, а не ошибку сборки. Все6 проб разности совпали с полными ожидаемыми множествами. Последний distinct-output MxM по-прежнему выдаёт3 пары вместо5. На atom base/incremental/lazy все дали6 (эталон). Это не полная GPU-корректность и не performance baseline. manifest содержит команды и SHA256 новой библиотеки/бинарника, JSON — stdout/stderr и результаты. Старые артефакты не перезаписаны.

```bash
python3 /mnt/d/semen_task_avtomat/scripts/check-cubool-update.py
```
