# Zero-fill: ранний выход при пустом произведении

Дата:2026-11-10. База52e2ef8,веткаresearch/gpu-empty-fill. Изолированная trial-библиотека, production не изменён.

## Гипотеза и семантика

Предыдущая диагностика позднего luindex нашла17323случая product.empty/C.empty. Хотя merge там уже обходится, fill_nz выполняет подготовкуbins/scan/permutation до чтения итогового размера. Кандидат—перенести существующее чтениеrow_idx.back()передбиннингом и при0вернутьпустойcolvector. Весь count_nz остаётся; это не пропуск вычисления произведения до подсчёта.

CSRrow_idx—готовыйexclusiveprefixsumнеотрицательныхсчётчиковстрок. Еслипоследнийэлемент0,всесчётчики0,столбцовдляfillнет. Row_idx остаётся вres,изменение возвращает только пустойcolvector;числострок/столбцовматрицы не меняется. Дальнейшийreuse_global_hash_table иmerge сохраняются. ЕслиCнепустая,ветвьmergeнеобходитсяэтимпатчем. На ненулевомпродукте выполняетсяпрежнийfill. Чтение итогового счётчика перенесено, а не добавлено второе чтение. Порядок CPU/GPU-синхронизаций может измениться, проверяется фактическая корректность.

Это единственная содержательная правка:fill_nz.hвкопииbuild/gpu-empty-fill. Metadata/streamreuse/alias/tileне включены. База содержит ранее провереннуюrowmask. Пересобран толькоmultiplyobject,остальныеобъектыизbaseline. SHA256/compile/link:manifest.json,build-commands.json;patch:empty-fill.patch. Исходныебиблиотеки/headersне меняются.

## Выполненные команды

```bash
python3 /mnt/d/semen_task_avtomat/scripts/trial-gpu-bin-metadata.py --empty-fill
python3 /mnt/d/semen_task_avtomat/scripts/check-gpu-bin-metadata.py --empty-fill
python3 /mnt/d/semen_task_avtomat/scripts/trace-bin-metadata.py --empty-fill
python3 /mnt/d/semen_task_avtomat/scripts/check-metadata-luindex.py --empty-fill
```

Имена скриптов исторические; --empty-fill выбирает отдельныеbuild/output и не включаетmetadatapatch. CUDA12.4/RTX3060Laptop/driver621.01/WSL2Ubuntu;ReleaseCUDA-only,sequentialOFF,флагиизbaseline flags.make. Сборкаexit0,build.logпуст. Источникивходов/эталоны/labels/SHA: ../2026-11-03-trial-catalog/inputs.json. Грамматики/epsilon/вершинынеизменены. Матричныепроверкисравниваютмножества/nvals,CFPQ—количества.

## Проверки и измерения

Baseline/trial:C++2/2,примитивы24/24,границы138/138,alias622/864(все242известныенесовпадениятолькоnonaccumulatealias). Distinct-output/accumulateпрошли. Trial12/12малыхвнешнихконфигураций:atom6,bzip315,pizza1356,gzip1458 ×3алгоритма.

Pizza/incremental:по1прогреву+5измерений,порядокчередуется,безпрофиля. Полноеwallвремяsubprocessдофинализации,сновымcontextкаждыйраз;прогревсистемныхкэшей,необщегоCUDAcontext. Baseline median0.547123с[0.514608,0.692822],trial0.531500с[0.473039,0.625946]. Диапазоныперекрываются,устойчивыйspeedupне заявляется. Предыдущие прогоны других trialне включаются в агрегаты.

Отдельно дваполныхpizzaCUDAtrace(Nsight2026.1.3,cuda,sample=none,cpuctxsw=none),обаprofile/stats0,ответ1356. Сравнение одной и той же завершённой задачи:

| CUDA API count | Baseline | Trial |
|---|---:|---:|
| LaunchKernel |436|420|
| StreamSynchronize |701|671|
| Malloc/Free |287/287|279/279|
| MemcpyAsync |369|353|
| MemsetAsync |35|33|
| StreamCreate/Destroy |90/90|90/90|

Профиль подтверждает снижениечислаопераций,не ускорение. Точныеcommands/CSV/countsвtrace-comparison.json иbaseline/trial-trace-stats.csv. Бинарныеnsysrep/sqliteтольковbuild/gpu-empty-fill-trace.

Большойluindex:выполненаоднапараtrial→baseline,с300слимитомнакаждый,безпрогрева/профиля. Обаexit0,9677;trialwall111.742017с(Analysis111.193),baselinewall175.910395с. Runner0,hashes_unchanged=true. Полнаякоманда/граф/грамматика/бинарники/библиотекиSHA256/сырыеstdout/stderr—luindex-pair.json. Ответсверенпоколичеству,немножествуCFPQ.

Внутриэтойпарыотношениеwallвремёноколо1.574,trialна36.5%быстрее. Это наблюдение,неподтверждённыйустойчивыйspeedup:фиксированныйпорядок,одинповтор,нефиксированныечастоты/внешняянагрузка,историческинаблюдалисьтаймауты. Предыдущиерезультатыметаданных/диагностическихверсийнеподмешиваютсявстатистику. Профильpizzaиluindexвыполнялисьпоследовательно,непараллельно.

## Вывод и следующий шаг

Раннийвыходfillпринулевомразмерекорректеннавыбранныхматричныхпроверках,12малыхвнешнихконфигурацияхиluindex. Механизмподтверждёнснижениемkernel/APIcountнаполнойодинаковойpizzaзадаче. Большойграфпоказалзаметнуюразницувремени,ноустойчивостьещёнужнопроверить. Следующийшаг—прогревипарысобратнымпорядкомвстабильныхусловиях;при подтверждении—отдельнаяполнаясборкакандидата. Productionнеизменён,aliasконтрактпо-прежнемуотдельнаязадача. Sanitizerнедоступенвпрежнемокружении,здесьповторнонеиспользовался. ОбщаяGPUкорректность/причинастарыхтаймаутовнеустановлены.
