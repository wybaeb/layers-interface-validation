#!/usr/bin/env python3
"""Prepare and process tree testing before static-screen validation."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import shutil
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from run_study import resolve_user_path
from validation_lab import LabError, _gallery, build_screen_map

TOOL_VERSION = "2026.11.09.5"

@dataclass
class Node:
    label: str
    node_id: str
    children: list["Node"] = field(default_factory=list)


def _slug(value: str) -> str:
    value = re.sub(r"[*_`~]", "", value).lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", "-", value, flags=re.I).strip("-")
    return value or "node"


def _clean_label(value: str) -> str:
    value = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_`~]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _tree_lines(markdown: str) -> list[str]:
    lines = markdown.replace("\r", "").splitlines()
    start = next((i for i, line in enumerate(lines)
                  if re.match(r"^#{1,6}\s+.*(?:дерев|структур|навигац)", line, re.I)), None)
    if start is None:
        return lines
    level = len(lines[start].split(maxsplit=1)[0])
    end = len(lines)
    for i in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[i])
        if match and len(match.group(1)) <= level:
            end = i
            break
    return lines[start + 1:end]


def parse_ia(markdown: str) -> Node:
    """Parse a Markdown bullet tree without requiring technical IDs from students."""
    rows: list[tuple[int, str]] = []
    for raw in _tree_lines(markdown):
        match = re.match(r"^(\s*)(?:[-+*]|\d+[.)])\s+(.+?)\s*$", raw)
        if not match:
            continue
        indent = len(match.group(1).replace("\t", "  "))
        label = _clean_label(match.group(2))
        if label:
            rows.append((indent // 2, label))
    if not rows:
        raise LabError("в ia.md не найдено дерево в виде маркированного списка с отступами")
    min_depth = min(depth for depth, _ in rows)
    rows = [(max(0, depth - min_depth), label) for depth, label in rows]
    virtual_root = sum(depth == 0 for depth, _ in rows) > 1
    root = Node("Продукт", "root")
    stack: list[tuple[int, Node, list[str]]] = [(-1, root, [])]
    used: dict[str, int] = {}
    for depth, label in rows:
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent_depth, parent, path = stack[-1]
        node_path = [*path, label]
        base = _slug("-".join(node_path))
        used[base] = used.get(base, 0) + 1
        node_id = base if used[base] == 1 else f"{base}-{used[base]}"
        node = Node(label, node_id)
        parent.children.append(node)
        stack.append((depth, node, node_path))
    if not virtual_root and len(root.children) == 1:
        only = root.children[0]
        only.node_id = "root"
        return only
    return root


def flatten(root: Node) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(node: Node, path: list[str]) -> None:
        current = [*path, node.label]
        rows.append({"id": node.node_id, "label": node.label, "path": current})
        for child in node.children:
            visit(child, current)

    visit(root, [])
    return rows


def node_to_dict(node: Node) -> dict[str, Any]:
    return {
        "id": node.node_id,
        "label": node.label,
        "children": [node_to_dict(child) for child in node.children],
    }


def _read_optional(study: Path, names: tuple[str, ...]) -> str:
    for name in names:
        path = study / name
        if path.is_file() and path.stat().st_size:
            return path.read_text(encoding="utf-8")
    return ""


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _verify_sources(study: Path, manifest: dict[str, Any], manifest_path: Path | None = None) -> None:
    ia = study / "ia.md"
    screens = study / "screens"
    if not manifest.get("source_ia_sha256") or not isinstance(manifest.get("screen_hashes"), dict):
        if not ia.is_file() or not screens.is_dir():
            raise LabError("нельзя обновить контроль исходников: ia.md или screens/ отсутствуют")
        manifest["source_ia_sha256"] = _sha256(ia)
        manifest["screen_hashes"] = {
            path.name: _sha256(path)
            for path in screens.glob("*.svg")
            if path.is_file()
        }
        if manifest_path is not None:
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print("Обновлён манифест предыдущей версии; результаты исследования сохранены.")
    if not ia.is_file() or _sha256(ia) != manifest.get("source_ia_sha256"):
        raise LabError("исходный ia.md изменился после подготовки; сбросьте research и начните заново")
    expected = manifest.get("screen_hashes", {})
    current = {
        path.name: _sha256(path)
        for path in (study / "screens").glob("*.svg")
        if path.is_file()
    }
    if current != expected:
        raise LabError("набор исходных SVG изменился после подготовки; сбросьте research и начните заново")


def _task_prompt(ia: str, flow: str, nodes: list[dict[str, Any]]) -> str:
    labels = "\n".join(f"- {row['label']}" for row in nodes if row["id"] != "root")
    return f"""# Подготовка исследования структуры и экранов

Работайте только с переданными материалами одного продукта. Не добавляйте функции, которых нет в информационной архитектуре, пользовательском маршруте или экранах.

## 1. Задания для tree testing

Сформируйте задания, которые покрывают основные ветви дерева. Не фиксируйте количество участников: исследователь проведёт столько сессий, сколько уместно для его проекта. Каждое задание:

- описывает ситуацию и цель пользователя;
- не повторяет название правильного раздела;
- ведёт к одному существующему узлу дерева.

Сохраните результат в `research/tree_tasks.json` строго в формате:

```json
{{"tasks":[{{"id":"T-01","prompt":"Ситуация и цель пользователя","targetLabel":"Точное название узла"}}]}}
```

Допустимые названия узлов:
{labels}

## 2. Задания для проверки экранов

Сформируйте короткий сценарий модератора и сохраните его в `research/questionnaire.md`. Для каждого задания укажите цель участника, нейтральную формулировку без подсказки и ожидаемый наблюдаемый результат. Не просите участника оценивать вкус автора.

## Информационная архитектура

{ia.strip()}

## Пользовательский маршрут

{flow.strip() or 'Не передан. Опирайтесь на информационную архитектуру и экраны.'}
"""


def preflight(study: Path) -> bool:
    ia = study / "ia.md"
    screens = study / "screens"
    svg_count = len(list(screens.glob("*.svg"))) if screens.is_dir() else 0
    rows = [
        ("Информационная архитектура", ia, ia.is_file() and ia.stat().st_size > 0,
         "положите актуальный ia.md в папку исследования"),
        ("Экраны", screens, screens.is_dir() and svg_count > 0,
         "положите в screens/ хотя бы один SVG"),
    ]
    print("PREFLIGHT · подготовка исследования")
    print("| Вход | Путь | Статус | Что сделать |")
    print("|---|---|---|---|")
    for label, path, found, action in rows:
        print(f"| {label} | `{path.as_posix()}` | {'найден' if found else 'отсутствует'} | {'ничего' if found else action} |")
    passed = all(row[2] for row in rows) and not (study / "research").exists()
    if (study / "research").exists():
        print(f"| Результаты подготовки | `{(study / 'research').as_posix()}` | уже существуют | выполните --reset-research, если хотите начать заново |")
    print("\n" + ("PREFLIGHT PASS" if passed else "PREFLIGHT STOP"))
    return passed


def prepare(study: Path) -> None:
    if not preflight(study):
        raise LabError("подготовка остановлена: исправьте входы или освободите папку research")
    ia = (study / "ia.md").read_text(encoding="utf-8")
    root = parse_ia(ia)
    nodes = flatten(root)
    research = study / "research"
    research.mkdir()
    rows = build_screen_map(study / "screens")
    (research / "gallery.html").write_text(_gallery(rows), encoding="utf-8")
    flow = _read_optional(study, ("user_flow.md", "screen_flow.md", "screen_flow.txt"))
    (research / "prepare_tasks_prompt.md").write_text(_task_prompt(ia, flow, nodes), encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "tree": node_to_dict(root),
        "nodes": nodes,
        "screen_count": len(rows),
        "source_ia": "../ia.md",
        "source_ia_sha256": _sha256(study / "ia.md"),
        "screen_hashes": {row["file"]: row["sha256"] for row in rows},
    }
    (research / "research_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("RESEARCH PREPARED")
    print(f"Галерея: {(research / 'gallery.html').as_posix()}")
    print(f"Запрос агенту: {(research / 'prepare_tasks_prompt.md').as_posix()}")


def _load_tasks(research: Path, nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    path = research / "tree_tasks.json"
    if not path.is_file():
        raise LabError(f"нет {path}; сначала выполните prepare_tasks_prompt.md")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    tasks = parsed.get("tasks") if isinstance(parsed, dict) else parsed
    if not isinstance(tasks, list) or not tasks:
        raise LabError("tree_tasks.json должен содержать непустой массив tasks")
    by_label = {row["label"].casefold(): row for row in nodes}
    result = []
    for index, task in enumerate(tasks, 1):
        if not isinstance(task, dict):
            raise LabError(f"задание {index}: ожидается объект")
        prompt = str(task.get("prompt", "")).strip()
        label = str(task.get("targetLabel", "")).strip()
        target = by_label.get(label.casefold())
        if not prompt or not target or target["id"] == "root":
            raise LabError(f"задание {index}: проверьте prompt и точное targetLabel из дерева")
        result.append({
            "id": str(task.get("id") or f"T-{index:02d}"),
            "prompt": prompt,
            "targetId": target["id"],
            "targetLabel": target["label"],
        })
    return result


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace("-->", "--\\u003e")


def _tree_test_html(config: dict[str, Any]) -> str:
    title = html.escape(config["title"])
    data = _safe_json(config)
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Проверка структуры · {title}</title><style>
*{{box-sizing:border-box}}:root{{--bg:#1e2027;--panel:#292d36;--ink:#f3f4f7;--muted:#b5bcc8;--accent:#ff5533;--line:#596171}}body{{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 system-ui,sans-serif}}main{{max-width:820px;margin:auto;padding:36px 20px 70px}}h1{{font-size:36px;line-height:1.1}}section{{background:var(--panel);padding:24px;border-radius:14px;margin:18px 0}}.muted{{color:var(--muted)}}label{{display:block;font-weight:700;margin:12px 0 6px}}input{{width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:#181a20;color:var(--ink);font:inherit}}button{{font:inherit;color:var(--ink);border:1px solid #707a8e;background:transparent;border-radius:9px;padding:11px 14px;cursor:pointer}}button.primary{{background:var(--accent);color:#1e2027;border-color:var(--accent);font-weight:800}}.choices{{display:grid;gap:10px;margin:18px 0}}.choices button{{text-align:left}}.crumbs{{display:flex;gap:7px;flex-wrap:wrap}}.crumbs button{{padding:5px 8px;font-size:14px}}.actions{{display:flex;gap:10px;flex-wrap:wrap}}.hidden{{display:none}}.progress{{color:var(--accent);font-weight:800}}.done{{border-left:4px solid #91c6aa}}@media(max-width:600px){{main{{padding:24px 12px}}h1{{font-size:30px}}section{{padding:18px}}}}
</style></head><body><main><p class="progress">LAYERS · TREE TESTING</p><h1>{title}</h1><p>Выполняйте задания по одному. Вы увидите только названия разделов, без экранов интерфейса.</p>
<section id="start"><label for="participant">Код участника без имени и контактов</label><input id="participant" value="R1"><p class="muted">Например, R1. Код нужен только для разделения сессий.</p><button class="primary" id="begin">Начать</button></section>
<section id="task" class="hidden"><p class="progress" id="counter"></p><h2 id="prompt"></h2><div class="crumbs" id="crumbs"></div><div class="choices" id="choices"></div><div class="actions"><button id="choose">Выбрать текущий раздел</button><button id="back">Назад</button></div></section>
<section id="done" class="hidden done"><h2>Сессия завершена</h2><p>Скачайте результат и передайте файл исследователю.</p><div class="actions"><button class="primary" id="download">Скачать результат</button><button id="again">Новый участник</button></div></section>
<script>const STUDY={data};let participant='',index=0,current=STUDY.tree,path=[],started=0,backtracks=0,firstChoice=null,results=[];const $=id=>document.getElementById(id);function render(){{const task=STUDY.tasks[index];$('counter').textContent='Задание '+(index+1)+' из '+STUDY.tasks.length;$('prompt').textContent=task.prompt;$('crumbs').innerHTML='';path.forEach((node,i)=>{{const b=document.createElement('button');b.textContent=node.label;b.onclick=()=>{{if(i<path.length-1)backtracks+=1;path=path.slice(0,i+1);current=path.at(-1);render()}};$('crumbs').appendChild(b)}});$('choices').innerHTML='';current.children.forEach(child=>{{const b=document.createElement('button');b.textContent=child.label;b.onclick=()=>{{if(!firstChoice)firstChoice=child.label;current=child;path.push(child);render()}};$('choices').appendChild(b)}});$('choose').disabled=current.id==='root'}}function resetTask(){{current=STUDY.tree;path=[STUDY.tree];started=Date.now();backtracks=0;firstChoice=null}}function next(){{const task=STUDY.tasks[index];results.push({{taskId:task.id,targetId:task.targetId,selectedId:current.id,success:current.id===task.targetId,backtracks,firstChoiceLabel:firstChoice,pathLabels:path.map(n=>n.label),durationSeconds:Math.max(1,Math.round((Date.now()-started)/1000))}});index+=1;if(index>=STUDY.tasks.length){{$('task').classList.add('hidden');$('done').classList.remove('hidden');return}}resetTask();render()}}$('begin').onclick=()=>{{participant=$('participant').value.trim()||'R';index=0;results=[];resetTask();$('start').classList.add('hidden');$('task').classList.remove('hidden');render()}};$('choose').onclick=next;$('back').onclick=()=>{{if(path.length>1){{path.pop();current=path.at(-1);backtracks+=1;render()}}}};$('download').onclick=()=>{{const payload={{schemaVersion:1,studyId:STUDY.id,participantId:participant,completedAt:new Date().toISOString(),results}},blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='tree-result-'+participant+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};$('again').onclick=()=>{{$('done').classList.add('hidden');$('start').classList.remove('hidden')}};</script></main></body></html>'''


def build_tree_test(study: Path) -> None:
    research = study / "research"
    manifest_path = research / "research_manifest.json"
    if not manifest_path.is_file():
        raise LabError("сначала выполните --prepare-research")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_sources(study, manifest, manifest_path)
    tasks = _load_tasks(research, manifest["nodes"])
    config = {
        "schemaVersion": 1,
        "id": _slug(study.name),
        "title": study.name.replace("_", " ").strip().title(),
        "tree": manifest["tree"],
        "tasks": tasks,
    }
    # The target remains available to the runner for scoring, but its human-readable
    # label is not embedded in the participant page.
    runner_config = {
        **config,
        "tasks": [
            {key: value for key, value in task.items() if key != "targetLabel"}
            for task in tasks
        ],
    }
    (research / "tree_test.html").write_text(_tree_test_html(runner_config), encoding="utf-8")
    (research / "tree_study.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (research / "tree_responses").mkdir(exist_ok=True)
    print("TREE TEST READY")
    print(f"Откройте: {(research / 'tree_test.html').as_posix()}")
    print(f"Результаты сессий складывайте в: {(research / 'tree_responses').as_posix()}")


def _median(values: list[float]) -> str:
    return "нет данных" if not values else f"{round(statistics.median(values))} с"


def summarize_tree_test(study: Path) -> None:
    research = study / "research"
    config_path = research / "tree_study.json"
    responses = research / "tree_responses"
    if not config_path.is_file():
        raise LabError("нет tree_study.json; сначала выполните --build-tree-test")
    files = sorted(responses.glob("*.json")) if responses.is_dir() else []
    if not files:
        raise LabError("нет результатов в research/tree_responses; проведите хотя бы одну сессию")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = json.loads((research / "research_manifest.json").read_text(encoding="utf-8"))
    _verify_sources(study, manifest, research / "research_manifest.json")
    sessions = []
    for path in files:
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("studyId") != config["id"]:
            raise LabError(f"{path.name}: результат относится к другому исследованию")
        sessions.append(row)
    lines = [
        f"# Tree testing · {config['title']}", "",
        "## Условия проверки", "",
        f"- Сессий: {len(sessions)}.",
        f"- Заданий: {len(config['tasks'])}.",
        "- Участники видели только текстовое дерево без экранов интерфейса.", "",
        "## Результаты", "",
        "| Задание | Успешно | Прямой путь | Медианное время | Повторяющиеся первые выборы |", "|---|---:|---:|---:|---|",
    ]
    for task in config["tasks"]:
        rows = [result for session in sessions for result in session.get("results", []) if result.get("taskId") == task["id"]]
        success = sum(bool(row.get("success")) for row in rows)
        direct = sum(bool(row.get("success")) and int(row.get("backtracks", 0)) == 0 for row in rows)
        times = [float(row["durationSeconds"]) for row in rows if isinstance(row.get("durationSeconds"), (int, float))]
        choices: dict[str, int] = {}
        for row in rows:
            label = row.get("firstChoiceLabel") or "не зафиксирован"
            choices[label] = choices.get(label, 0) + 1
        choice_text = "; ".join(f"{label} — {count}" for label, count in sorted(choices.items(), key=lambda x: -x[1]))
        prompt = task["prompt"].replace("|", "\\|")
        lines.append(f"| {task['id']}: {prompt} | {success}/{len(rows)} | {direct}/{len(rows)} | {_median(times)} | {choice_text or 'нет данных'} |")
    lines += [
        "", "## Маршруты участников", "",
    ]
    for session in sessions:
        participant = session.get("participantId", "участник")
        for result in session.get("results", []):
            route = " → ".join(result.get("pathLabels") or []) or "маршрут не зафиксирован"
            lines.append(f"- **{participant}, {result.get('taskId', 'задание')}:** {route}.")
    lines += [
        "", "## Наблюдения и решения", "",
        "Заполните этот раздел после проверки маршрутов. Отделяйте наблюдаемое действие от возможной причины. Изменяйте информационную архитектуру только там, где результат подтверждается проведёнными сессиями.", "",
        "## Информационная архитектура после проверки", "",
        "После принятия решений сохраните обновлённую версию в `ia_after_tree_testing.md`. Исходный `ia.md` инструмент не перезаписывает.", "",
    ]
    report = research / "tree_testing.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    ia = (study / "ia.md").read_text(encoding="utf-8")
    revised = research / "ia_after_tree_testing.md"
    if not revised.exists():
        revised.write_text(ia, encoding="utf-8")
    prompt = f"""# Интерпретация tree testing

Работайте только с файлами в `{research.as_posix()}`. Прочитайте `tree_testing.md`, `tree_study.json`, все JSON из `tree_responses/` и исходный `{(study / 'ia.md').as_posix()}`.

1. Дополните раздел «Наблюдения и решения» в `tree_testing.md`. Для каждой существенной трудности свяжите задание, фактический маршрут, первый выбор, возвраты и решение. Не называйте возможную причину фактом.
2. Если данные обосновывают изменение структуры, внесите его в `ia_after_tree_testing.md`. Не меняйте исходный `ia.md` автоматически.
3. Если изменение не подтверждено, оставьте структуру без изменений и прямо укажите это в отчёте.
4. Не фиксируйте требуемое количество участников и не добавляйте сведения, которых нет в результатах.
"""
    (research / "interpret_tree_testing_prompt.md").write_text(prompt, encoding="utf-8")
    print("TREE TESTING REPORT READY")
    print(f"Фактический отчёт: {report.as_posix()}")
    print(f"Запрос для интерпретации: {(research / 'interpret_tree_testing_prompt.md').as_posix()}")


def validate_tree_report(study: Path) -> None:
    research = study / "research"
    manifest_path = research / "research_manifest.json"
    study_path = research / "tree_study.json"
    report_path = research / "tree_testing.md"
    revised_path = research / "ia_after_tree_testing.md"
    for path in (manifest_path, study_path, report_path, revised_path):
        if not path.is_file() or not path.stat().st_size:
            raise LabError(f"нет обязательного результата: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_sources(study, manifest, manifest_path)
    config = json.loads(study_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    required = (
        "## Условия проверки",
        "## Результаты",
        "## Маршруты участников",
        "## Наблюдения и решения",
        "## Информационная архитектура после проверки",
    )
    missing = [heading for heading in required if heading not in report]
    if missing:
        raise LabError("в tree_testing.md нет разделов: " + ", ".join(missing))
    if "Заполните этот раздел после проверки маршрутов" in report:
        raise LabError("раздел наблюдений ещё не обработан агентом")
    for task in config.get("tasks", []):
        if str(task.get("id", "")) not in report:
            raise LabError(f"в tree_testing.md не разобрано задание {task.get('id')}")
    parse_ia(revised_path.read_text(encoding="utf-8"))
    print("TREE REPORT PASS")
    print(f"Отчёт: {report_path}")
    print(f"Архитектура после проверки: {revised_path}")


def reset_research(study: Path) -> None:
    target = study / "research"
    if target.is_symlink():
        raise LabError("research не должна быть символической ссылкой")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        raise LabError("research существует, но не является папкой")
    print("Подготовка исследования сброшена. Исходные ia.md и screens/ сохранены.")


def cli() -> int:
    parser = argparse.ArgumentParser(description="Подготовить tree testing и проверку экранов")
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    parser.add_argument("study", help="абсолютный путь или путь от корня студенческого репозитория")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--preflight-research", action="store_true")
    action.add_argument("--prepare-research", action="store_true")
    action.add_argument("--build-tree-test", action="store_true")
    action.add_argument("--summarize-tree-test", action="store_true")
    action.add_argument("--validate-tree-report", action="store_true")
    action.add_argument("--reset-research", action="store_true")
    args = parser.parse_args()
    study = resolve_user_path(args.study)
    try:
        if args.preflight_research:
            return 0 if preflight(study) else 2
        if args.prepare_research:
            prepare(study)
        elif args.build_tree_test:
            build_tree_test(study)
        elif args.summarize_tree_test:
            summarize_tree_test(study)
        elif args.validate_tree_report:
            validate_tree_report(study)
        elif args.reset_research:
            reset_research(study)
        return 0
    except (LabError, ValueError, json.JSONDecodeError, OSError) as error:
        print(f"Ошибка: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
