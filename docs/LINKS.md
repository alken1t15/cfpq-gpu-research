# Важные ссылки

Проверено повторно 2026-11-03: доступ восстановлен. CFRA клонирован, README примера и HTML каталога сохранены в `docs/sources/`. Предыдущие ошибки были ограничением среды.

| Ресурс | Ссылка | Зачем нужен |
|---|---|---|
| Исходный GPU CFPQ проект | https://github.com/vano105/cfra | Клонирование, изучение алгоритма, сборки, тестов, зависимостей и лицензии |
| Каталог экспериментальных данных | https://formallanguageconstrainedpathquerying.github.io/FLPQ_Data/dataset.html | Выбор графов и грамматик, форматов и опубликованных контрольных результатов |
| Переданная ссылка на раздел каталога | https://formallanguageconstrainedpathquerying.github.io/FLPQ_Data/dataset.html#how-to-add-a-new-grammar | Сохранён исходный якорь; он относится к добавлению грамматики, а не обязательно к скачиванию данных |
| Пример оформления | https://github.com/RodionovMaxim05/cfl-idr-with-gll#cfl-idr-with-gll | Изучены постановка, описание оборудования, таймаутов, повторов и структура анализа. Задача IDR отличается; это пример оформления, не готовый baseline |


Нужно получить позднее: URL репозитория сообщества, точную статью про оптимизации, адрес собственного форка. Не подставлять предполагаемые ссылки вместо неизвестных.


## Уточнённые ссылки после чтения

- Библиотека: https://github.com/SparseLinearAlgebra/cuBool
- Репозиторий оптимизаций И. Муравьёва, указанный CFRA: https://github.com/FormalLanguageConstrainedPathQuerying/CFPQ_PyAlgo
- Каталог графов: https://formallanguageconstrainedpathquerying.github.io/FLPQ_Data/graphs/index.html
- CFPQ-запросы: https://formallanguageconstrainedpathquerying.github.io/FLPQ_Data/queries/cfpq/index.html
- Контрольные количества пар: https://formallanguageconstrainedpathquerying.github.io/FLPQ_Data/reachable_pairs.html

Каталоги графов и CFPQ и таблица контрольных количеств прочитаны; для atom/bzip данные скачаны и проверены. Старого якоря `how-to-add-a-new-grammar` в текущем HTML нет; раздел добавления данных теперь указан как `contributing_data.html`.

Контрольная таблица v6: https://cfpq-data.storage.yandexcloud.net/6.0.0/reachable_pairs.csv

Проверенный Java-граф: https://formallanguageconstrainedpathquerying.github.io/FLPQ_Data/graphs/data/luindex.html
Архив luindex v6: https://cfpq-data.storage.yandexcloud.net/6.0.0/graph/luindex.tar.gz

Официальное руководство CUDA/WSL (изучено при подготовке среды): https://docs.nvidia.com/cuda/wsl-user-guide/index.html
Официальный SDK apt repo: https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/

