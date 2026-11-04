# CPU smoke-test в WSL с GCC 13

Дата: 2026-11-03. Статус: успешно, код завершения 0.
Цель: собрать неизменённый исходный CFRA и выполнить шесть штатных проверок. Это не performance baseline.

Код: main, SHA `3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1`; cuBool `1d4e760bc0d76906b81c70c505d6b29b4d9d3f11`.
Ubuntu 22.04 WSL2, CMake 3.22.1, GCC 13.4.0, CPU i7-11370H. Подробности: environment.log.

## Подготовка toolchain (выполнено успешно)

```bash
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends g++-13
```

Установлены GCC/G++ 13.4.0 и libstdc++-13-dev из PPA Ubuntu Toolchain. APT также обновил девять runtime-пакетов, включая libstdc++6 до `16-20260315-1ubuntu1~22~ppa1`. Полный список и вывод — toolchain-install.log. Системный `g++` остаётся 11.4.0; сборка явно выбирает g++-13. PPA остался подключённым.

## Воспроизведение из PowerShell

```powershell
wsl -d Ubuntu -- bash /mnt/d/semen_task_avtomat/scripts/wsl-cpu-smoke.sh
```

Скрипт задаёт Release, gcc-13/g++-13, CUDA OFF, тесты самой cuBool OFF, копирование Python-пакета OFF. Каталог `src/cfra/build-cpu-gcc13`. В исходном тестовом скрипте жёстко задан `build/cfra`; при запуске через поток заменяется только путь и нормализуются CRLF. Все шесть проверок upstream остаются прежними. Исходники не меняются. Сборочный каталог исключён локально через `.git/info/exclude`.

Первый запуск прервался до окончания конфигурации; причина не установлена, активного процесса при продолжении сессии не было. Частичный лог: build-test.log. Повторный запуск: build-test-retry.log.

## Корректность и ограничения

Штатный набор сверяет только количества пар на двух графах, по три алгоритма; независимым доказательством корректности это не является. GPU, внешние данные и производительность здесь не проверяются.

## Результат

Повторная сборка успешна: `6 passed, 0 failed`. Все три алгоритма дали 20 для an_bn и 21 для transitive_loop. Полный лог: [build-test-retry.log](build-test-retry.log).

Дополнительно выполнено:

```powershell
wsl -d Ubuntu -- python3 /mnt/d/semen_task_avtomat/scripts/check-small-cpu.py
```

Независимый Python oracle строит замыкание на множествах пар по явно заданным двум грамматикам. Все шесть сравнений количества пар совпали. Полные пары oracle и stdout каждого запуска: [independent-checks.json](independent-checks.json).
Ограничение: CFRA CLI выводит только количество, поэтому равенство самих множеств пар CFRA не проверено. Проверка охватывает только два малых графа, не шаблонные грамматики и не GPU. Времена в stdout не используются как baseline.
