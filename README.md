# Проверка структуры и интерфейса

Один лончер связывает два исследования одного продукта:

1. tree testing актуальной информационной архитектуры;
2. коридорную проверку экранов по обычному транскрипту.

Страница лончера публикуется из `index.html`. Инструменты лежат в `interface_validation_lab/`.

## Быстрая проверка

```bash
python3 -m unittest discover -s interface_validation_lab/tests -v
```

Учебный пример создаётся командой:

```bash
python3 scripts/build_demo.py
```
