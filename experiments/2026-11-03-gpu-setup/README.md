# Подготовка GPU-среды в WSL

Дата: 2026-11-03. Цель: перейти от CPU fallback к проверяемому CUDA backend на локальной RTX3060 Laptop 6GiB.

## Установка

```powershell
wsl -d Ubuntu -- bash /mnt/d/semen_task_avtomat/scripts/setup-wsl-cuda.sh
```

По руководству NVIDIA https://docs.nvidia.com/cuda/wsl-user-guide/index.html в WSL используется Windows-драйвер; Linux display driver не устанавливался. Подключён официальный WSL-Ubuntu CUDA apt-репозиторий через cuda-keyring_1.1-1_all.deb. SHA256 keyring: eea6cc5f0eaeb99082d054b8c05ae206a378e31e88048df0310d59f651dceed2.
Установлены cuda-nvcc-12-4, cuda-cudart-dev-12-4, cuda-cccl-12-4, cuda-driver-dev-12-4 и зависимости: 10 пакетов, 54MB загрузки, 242MB места. cuda-driver-dev — заголовки/линковочные заглушки SDK, не Linux display driver. nvcc 12.4.131. Полный вывод и точные версии — install.log. APT создал /usr/local/cuda и /usr/local/cuda-12 как alternatives на cuda-12.4; PATH глобально не менялся. Репозиторий остался подключённым.

## Сборка

```powershell
wsl -d Ubuntu -- bash /mnt/d/semen_task_avtomat/scripts/build-wsl-gpu.sh
```

Отдельный каталог src/cfra/build-gpu-cuda124, локально исключён через .git/info/exclude. CPU baseline не перезаписывается. C/C++ compiler GCC13.4, CUDA host compiler GCC11.4, nvcc12.4, arch86 (RTX3060), Release. CUDA ON, **CPU sequential OFF**, тесты cuBool и копирование в Python OFF. Отключение CPU fallback обеспечивает, что неудача CUDA не будет выдана за успешный GPU-запуск.

CFRA содержит исправление/предупреждение шаблонов, базовый SHA 3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1; cuBool submodule 1d4e760bc0d76906b81c70c505d6b29b4d9d3f11 не изменён. CPU fast path не применяется к GPU-библиотеке: он меняет исключительно sequential backend.

Сборка успешно завершилась с кодом 0. Сборочные ошибки, если возникнут, не являются результатом экспериментов по производительности. Производительность на фоне установки/компиляции не измеряется.


## Проверка CUDA

cuBool_GetDeviceCaps подтвердил NVIDIA GeForce RTX3060 Laptop GPU, CUDA=true, capability8.6, 6290944KiB памяти. Manifest и хеши GPU-библиотеки/бинарника — ../2026-11-03-gpu-correctness/manifest.json. CPU fallback отключён при сборке.

Однако корректность не пройдена: прямые tiny-MxM-тесты дали 592/864 совпадений (matrix-all-results.json), первый провал alias-left сохранён также в matrix-test.log. Пробы с отдельной выходной матрицей: CPU24/24, GPU22/24 (primitive-cpu.json/primitive-gpu.json). Они воспроизводят A\empty=empty вместо A и потерю пар при nonalias MxM. Поэтому успешная сборка не трактуется как готовый корректный GPU solver.

Команды прямых проб:

```powershell
wsl -d Ubuntu -- python3 /mnt/d/semen_task_avtomat/scripts/probe-matrix-primitives.py /mnt/d/semen_task_avtomat/src/cfra/build-gpu-cuda124/cuBool/cubool/libcubool.so --gpu
wsl -d Ubuntu -- python3 /mnt/d/semen_task_avtomat/scripts/check-cubool-mxm-pairs.py /mnt/d/semen_task_avtomat/src/cfra/build-gpu-cuda124/cuBool/cubool/libcubool.so --gpu --collect-failures
```

Вторая команда возвращает код1 при несовпадениях; результаты сохранены, не считаются успешными тестами. Отдельное исправление GPU-разности и результат после него — ../2026-11-03-gpu-difference/.
