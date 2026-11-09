import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PYTHON=sys.executable
RESEARCH=ROOT/'interface_validation_lab'/'research_flow.py'
SCREEN=ROOT/'interface_validation_lab'/'run_study.py'

def run(*args):
    cp=subprocess.run([PYTHON,*map(str,args)],cwd=ROOT,text=True,capture_output=True)
    if cp.returncode:
        raise SystemExit(f"FAILED {args}\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    return cp.stdout

def svg(label):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><text x="10" y="30">{label}</text></svg>'

with tempfile.TemporaryDirectory() as tmp:
    study=Path(tmp)/'study with spaces'
    (study/'screens').mkdir(parents=True)
    (study/'screens'/'Главная.svg').write_text(svg('Главная'),encoding='utf-8')
    (study/'screens'/'Команда.svg').write_text(svg('Команда'),encoding='utf-8')
    (study/'ia.md').write_text('# Структура\n\n## Дерево\n\n- Продукт\n  - Главная\n  - Команда\n',encoding='utf-8')
    assert 'PREFLIGHT PASS' in run(RESEARCH,study,'--preflight-research')
    assert 'RESEARCH PREPARED' in run(RESEARCH,study,'--prepare-research')
    research=study/'research'
    (research/'tree_tasks.json').write_text('{"tasks":[{"id":"T-01","prompt":"Где найти команду?","targetLabel":"Команда"}]}',encoding='utf-8')
    assert 'TREE TEST READY' in run(RESEARCH,study,'--build-tree-test')
    config=json.loads((research/'tree_study.json').read_text(encoding='utf-8'))
    (research/'tree_responses'/'R1.json').write_text(json.dumps({"studyId":config['id'],"participantId":"R1","results":[{"taskId":"T-01","success":True,"backtracks":0,"firstChoiceLabel":"Команда","pathLabels":["Продукт","Команда"],"durationSeconds":8}]},ensure_ascii=False),encoding='utf-8')
    assert 'TREE TESTING REPORT READY' in run(RESEARCH,study,'--summarize-tree-test')
    (study/'transcript.md').write_text('# Проверка\n\nЭкран: Главная\n[00:01] R1: Открываю главный экран.\n\nЭкран: Команда\n[00:05] R1: Здесь вижу команду.\n',encoding='utf-8')
    assert 'PREFLIGHT PASS' in run(SCREEN,study,'--preflight')
    run(SCREEN,study)
    results=study/'results'
    manifest=json.loads((results/'workspace.json').read_text(encoding='utf-8'))
    report={
      'schema_version':1,'run_id':manifest['run_id'],'untrusted_inputs_acknowledged':True,
      'observations':[],
      'visual_review':[{'screen_id':row['screen_id'],'status':'inspected','method':'gallery_visual','note':'Экран открыт в автономной галерее.'} for row in manifest['screen_map']],
      'limitations':['В демонстрационном прогоне подтверждённых разрывов не обнаружено.'],
      'unlinked_evidence':[],'change_proposals':[],'insights':[],'prototype_brief':[]
    }
    (results/'draft_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    output=run(SCREEN,study,'--finish')
    assert 'CONTRACT PASS' in output
    for path in [research/'tree_test.html',research/'tree_testing.md',research/'ia_after_tree_testing.md',results/'РЕЗУЛЬТАТЫ.html']:
        assert path.is_file(), path
print('FULL FLOW PASS: inputs → tree test → tree report → transcript → validated screen report')
