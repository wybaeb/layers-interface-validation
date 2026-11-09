# Проверка структуры и интерфейса

Инструмент связывает два исследования одного продукта:

1. tree testing информационной архитектуры;
2. коридорную проверку статических экранов.

Работайте из корня студенческого репозитория. В папке исследования до начала нужны:

```text
interface_validation_lab/studies/my_study/
├── ia.md
└── screens/
    ├── Главная.svg
    └── Расписание.svg
```

`transcript.md` появится после проверки экранов. GitLab-логин и `git pull` для обновления инструмента не требуются: готовый запрос из лончера проверит версию и при необходимости установит проверяемый пакет.

## Подготовка исследований

```bash
python3 interface_validation_lab/research_flow.py --version
python3 interface_validation_lab/research_flow.py "interface_validation_lab/studies/my_study" --preflight-research
python3 interface_validation_lab/research_flow.py "interface_validation_lab/studies/my_study" --prepare-research
```

Выполните созданный `research/prepare_tasks_prompt.md`, затем соберите автономный tree test:

```bash
python3 interface_validation_lab/research_flow.py "interface_validation_lab/studies/my_study" --build-tree-test
```

Проведите tree testing через `research/tree_test.html`. Результаты сессий положите в `research/tree_responses/`. Проверку экранов проводите через автономный `research/gallery.html` по сценарию `research/questionnaire.md`; обезличенный транскрипт сохраните как `transcript.md`.

## Отчёт tree testing

```bash
python3 interface_validation_lab/research_flow.py "interface_validation_lab/studies/my_study" --summarize-tree-test
```

Выполните `research/interpret_tree_testing_prompt.md`, затем проверьте результаты:

```bash
python3 interface_validation_lab/research_flow.py "interface_validation_lab/studies/my_study" --validate-tree-report
```

Успешный результат начинается строкой `TREE REPORT PASS`. Исходный `ia.md` остаётся точкой возврата; предложенная версия сохраняется как `research/ia_after_tree_testing.md`.

## Отчёт по экранам

После появления `transcript.md` выполните:

```bash
python3 interface_validation_lab/run_study.py "interface_validation_lab/studies/my_study" --preflight
python3 interface_validation_lab/run_study.py "interface_validation_lab/studies/my_study"
```

Передайте агенту `results/cline_prompt.md`. После его ответа:

```bash
python3 interface_validation_lab/run_study.py "interface_validation_lab/studies/my_study" --finish
```

Успешный результат начинается строкой `CONTRACT PASS`. Основной отчёт находится в `results/РЕЗУЛЬТАТЫ.html`.

## Повторный запуск

Удалить только подготовку исследований:

```bash
python3 interface_validation_lab/research_flow.py "interface_validation_lab/studies/my_study" --reset-research
```

Удалить только результаты анализа экранов:

```bash
python3 interface_validation_lab/run_study.py "interface_validation_lab/studies/my_study" --reset
```

Исходные `ia.md`, SVG и `transcript.md` эти команды не удаляют.
