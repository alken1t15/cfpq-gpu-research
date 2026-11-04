# Первая попытка CPU-сборки

Дата: 2026-11-03. Статус: сборка CFRA заблокирована несовместимостью toolchain; тесты не запущены.
Цель — проверить исходную сборку без изменения алгоритма. Это не performance baseline.

Код: https://github.com/vano105/cfra, main, SHA `3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1`.
cuBool: `1d4e760bc0d76906b81c70c505d6b29b4d9d3f11`.
Исходники не менялись; `git status --short` пустой.
Среда: Ubuntu 22.04 в WSL2, Linux 5.15.167.4, GCC/libstdc++ 11.4.0, CMake 3.22.1.
Конфигурация взята из `.github/workflows/ci.yml` (фактическое имя файла см. в клоне).

## Команды

В PowerShell из корня рабочей папки:

```powershell
git clone https://github.com/vano105/cfra.git src/cfra
git -C src/cfra submodule update --init --recursive
```

В Ubuntu WSL, рабочая папка `/mnt/d/semen_task_avtomat/src/cfra`:

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release -DCUBOOL_WITH_CUDA=OFF -DCUBOOL_COPY_TO_PY_PACKAGE=OFF -DCUBOOL_BUILD_TESTS=OFF
cmake --build build -j4
# Следующая команда была в цепочке через &&, но не выполнилась:
bash ci/test.sh
```

## Наблюдаемый результат

Конфигурация успешна, cuBool собрана. CFRA не компилируется: `src/common.hpp:7:10: fatal error: format: No such file or directory`.
Сборочная цепочка завершилась с кодом 2. Полный вывод: [build-test.log](build-test.log).
CMake также сообщает предупреждение CMP0076; оно не остановило сборку.

## Вывод

Текущее окружение GCC 11.4 не поддерживает используемый здесь заголовок `<format>`; в `common.hpp` применяется `std::format`. Нужен совместимый toolchain/стандартная библиотека. Доступных g++-13/g++-14/clang++ в PATH не найдено; `/usr/include/c++` содержит только 11.
Это воспроизведённое препятствие сборки, не ошибка алгоритма. Ответы, времена и GPU не проверялись. Следующий шаг — выбрать и подготовить совместимый toolchain и повторить те же команды, сохранив исходный SHA.
