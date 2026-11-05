# Происхождение исходников

Код включён обычными файлами в основной репозиторий. После git clone не нужны submodule update или применение patches. Лицензии сохранены рядом с кодом.

| Каталог | Источник | Исходный SHA |
|---|---|---|
| src/cfra | https://github.com/vano105/cfra | 3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1 |
| src/cfra/cuBool | https://github.com/SparseLinearAlgebra/cuBool | 1d4e760bc0d76906b81c70c505d6b29b4d9d3f11 |
| src/cfra/cuBool/deps/gtest | https://github.com/google/googletest | 6910c9d9165801d8827d628cb72eb7ea9dd538c5 |

CFRA включает исправление шаблонов из patches/0001-*.patch. Патч теперь исторический артефакт: повторно применять его не нужно. Локальная Git-история сохранена в build/legacy-git-metadata. Тег baseline/cfra-upstream-2026-11-03 сохраняет исходный CFRA для исторического check-java-cpu.py.

Большой набор cuBool/python/data исключён. Python-тестам, использующим его, нужны данные отдельно. Остальные отслеживаемые файлы перенесены, кроме устаревших .gitmodules. Небольшие матрицы примеров python/examples сохранены.

Старые результаты и сборки относятся к исходной cuBool. После обновления библиотеки нужны новые сборки и протоколы. Все правки кода теперь коммитятся непосредственно в основном репозитории.
