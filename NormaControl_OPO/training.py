"""Human-approved local datasets and offline fine-tuning jobs (stdlib UI side)."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

from winproc import hidden


def _now():
    return datetime.now(timezone.utc).isoformat()


def _offline_env():
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1',
               HF_HUB_DISABLE_TELEMETRY='1', WANDB_DISABLED='true', OLLAMA_NO_CLOUD='1',
               OLLAMA_HOST='127.0.0.1:11434', PYTHONUNBUFFERED='1')
    return env


def _fields(task, context, answer, source_refs, reviewed, split):
    if split not in ('train', 'validation'):
        raise ValueError('Набор должен быть train или validation.')
    if not str(task).strip() or not str(answer).strip():
        raise ValueError('Задача и эталонный ответ обязательны.')
    return (str(task).strip(), str(context).strip(), str(answer).strip(), str(source_refs).strip(),
            int(bool(reviewed)), split)


def _key(row):
    # Whitespace/case variations of the same input cannot enter different splits.
    norm = lambda value: ' '.join(value.split()).casefold()
    return hashlib.sha256(json.dumps([norm(row['task']), norm(row['context'])],
                                    ensure_ascii=False).encode()).hexdigest()


class TrainingStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'promcontrol.sqlite3'
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS ai_examples (
                    id INTEGER PRIMARY KEY, task TEXT NOT NULL, context TEXT NOT NULL,
                    answer TEXT NOT NULL, source_refs TEXT NOT NULL DEFAULT '',
                    reviewed INTEGER NOT NULL DEFAULT 0, split TEXT NOT NULL DEFAULT 'train',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_training_jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, model_dir TEXT NOT NULL,
                    output_dir TEXT NOT NULL, started_at TEXT NOT NULL,
                    ended_at TEXT, log_path TEXT, result_json TEXT);
            ''')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_example(self, task, context, answer, source_refs='', reviewed=False, split='train'):
        values = _fields(task, context, answer, source_refs, reviewed, split)
        with self._connect() as db:
            return db.execute('INSERT INTO ai_examples(task,context,answer,source_refs,reviewed,split,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                              values + (_now(), _now())).lastrowid

    def examples(self):
        with self._connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM ai_examples ORDER BY id')]

    def update_example(self, id, task, context, answer, source_refs, reviewed, split):
        values = _fields(task, context, answer, source_refs, reviewed, split)
        with self._connect() as db:
            changed = db.execute('UPDATE ai_examples SET task=?,context=?,answer=?,source_refs=?,reviewed=?,split=?,updated_at=? WHERE id=?',
                                 values + (_now(), int(id))).rowcount
            if not changed:
                raise ValueError('Пример не найден.')

    def export_dataset(self, directory):
        groups = {'train': [], 'validation': []}
        seen = {}
        for row in self.examples():
            if not row['reviewed']:
                continue
            key = _key(row)
            if key in seen:
                previous = seen[key]
                if previous['split'] != row['split']:
                    raise ValueError('Утечка данных: одна задача/контекст присутствует в train и validation (примеры %s, %s).' % (previous['id'], row['id']))
                if previous['answer'] != row['answer']:
                    raise ValueError('Конфликт эталонных ответов (примеры %s, %s).' % (previous['id'], row['id']))
                continue
            seen[key] = row
            groups[row['split']].append(row)
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        result = {}
        for split, rows in groups.items():
            path = directory / (split + '.jsonl')
            temporary = path.with_suffix('.tmp')
            with temporary.open('w', encoding='utf-8') as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            temporary.replace(path)
            result[split] = str(path)
            result[split + '_count'] = len(rows)
        result['counts'] = {key: len(value) for key, value in groups.items()}
        result['paths'] = {key: result[key] for key in groups}
        return result

    def diagnostics(self):
        result = {'python': sys.version.split()[0], 'python_executable': sys.executable,
                  'cuda': False, 'mps': False, 'memory': None}
        for name in ('torch', 'transformers', 'peft', 'safetensors'):
            try:
                result[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                result[name] = None
        try:
            result['memory'] = {'ram_total_bytes': os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')}
        except (AttributeError, OSError, ValueError):
            # Windows: os.sysconf отсутствует; объём памяти и GPU — из локальной диагностики.
            from hardware import diagnose
            hardware = diagnose(self.root)
            if 'total_ram_gib' in hardware:
                result['memory'] = {'ram_total_bytes': int(hardware['total_ram_gib'] * 1024 ** 3),
                                    'ram_free_bytes': int(hardware['free_ram_gib'] * 1024 ** 3)}
            result['nvidia_smi'] = hardware.get('gpu') or hardware.get('gpu_error')
        if result['torch']:
            probe = '''import json,torch
r={'cuda':torch.cuda.is_available(),'mps':bool(hasattr(torch.backends,'mps') and torch.backends.mps.is_available())}
if r['cuda']:
 r['gpu_name']=torch.cuda.get_device_name(0)
 r['gpu_memory_free_bytes'],r['gpu_memory_total_bytes']=torch.cuda.mem_get_info()
print(json.dumps(r))'''
            try:
                proc = subprocess.run([sys.executable, '-c', probe], env=_offline_env(),
                                      capture_output=True, text=True, timeout=40, shell=False, **hidden())
                if proc.returncode == 0:
                    result.update(json.loads(proc.stdout.strip().splitlines()[-1]))
                else:
                    result['hardware_error'] = proc.stderr[-1000:]
            except (OSError, subprocess.TimeoutExpired, ValueError, IndexError) as exc:
                result['hardware_error'] = str(exc)
        result['recommendation'] = recommend_base(result.get('gpu_memory_free_bytes'), result.get('cuda'))
        return result

    def jobs(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM ai_training_jobs ORDER BY started_at DESC')]

    def run_training(self, model_dir, output_dir, epochs=1, max_length=512, progress=None,
                     cancel_event=None, timeout=7200):
        model_dir = Path(model_dir).resolve()
        if not model_dir.is_dir() or not (model_dir / 'config.json').is_file():
            raise ValueError('Нужна локальная папка модели Hugging Face с config.json, не GGUF Ollama.')
        if not 1 <= int(epochs) <= 20 or not 64 <= int(max_length) <= 8192:
            raise ValueError('Эпохи: 1–20; длина: 64–8192 токенов.')
        output = Path(output_dir).resolve()
        if output == model_dir or model_dir in output.parents or output in model_dir.parents:
            raise ValueError('Папки результата и исходной модели должны быть раздельными.')
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError('Выберите пустую папку результата: существующие артефакты не перезаписываются.')
        dataset = self.export_dataset(output / 'dataset')
        if not dataset['train_count'] or not dataset['validation_count']:
            raise ValueError('Нужны подтверждённые человеком примеры в обоих наборах: train и validation.')
        job_id = uuid.uuid4().hex
        log = output / 'training.log'
        command = [sys.executable, str(Path(__file__).with_name('train_lora.py')),
                   '--model-dir', str(model_dir), '--output-dir', str(output),
                   '--train', dataset['train'], '--validation', dataset['validation'],
                   '--epochs', str(int(epochs)), '--max-length', str(int(max_length))]
        with self._connect() as db:
            db.execute('INSERT INTO ai_training_jobs(id,status,model_dir,output_dir,started_at,log_path) VALUES(?,?,?,?,?,?)',
                       (job_id, 'running', str(model_dir), str(output), _now(), str(log)))
        result = {'job_id': job_id, 'log_path': str(log), 'output_dir': str(output)}
        proc = None
        try:
            start = time.monotonic()
            with log.open('w', encoding='utf-8') as stream:
                proc = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                        env=_offline_env(), shell=False, **hidden())
                last = ''
                while proc.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        result['status'] = 'cancelled'
                        break
                    if time.monotonic() - start > timeout:
                        result['status'] = 'timeout'
                        break
                    if progress:
                        tail = log.read_text(encoding='utf-8', errors='replace')[-3000:]
                        if tail != last:
                            progress(tail)
                            last = tail
                    time.sleep(0.25)
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                result.setdefault('status', 'completed' if proc.returncode == 0 else 'failed')
                result['returncode'] = proc.returncode
            result_path = output / 'result.json'
            if result['status'] == 'completed' and result_path.is_file():
                result.update(json.loads(result_path.read_text(encoding='utf-8')))
                result['status'] = 'completed'
                result['result_path'] = str(result_path)
            elif result['status'] == 'completed':
                result['status'] = 'failed'
                result['error'] = 'Процесс завершён без result.json.'
            else:
                result['error'] = log.read_text(encoding='utf-8', errors='replace')[-4000:]
        except Exception as exc:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
            result.update(status='failed', error=str(exc))
        finally:
            with self._connect() as db:
                db.execute('UPDATE ai_training_jobs SET status=?,ended_at=?,result_json=? WHERE id=?',
                           (result.get('status', 'failed'), _now(), json.dumps(result, ensure_ascii=False), job_id))
        return result

    def import_model(self, name, model_dir):
        return import_model(name, model_dir)


def recommend_base(free_vram_bytes, cuda):
    """Подбор размера базовой модели для LoRA bf16 (r=8, q_proj/v_proj, batch 1, до 512 токенов).

    Оценка: веса bf16 ≈ 2 байта на параметр плюс 15–25 % на активации/градиенты LoRA.
    Это ориентир, а не гарантия; Ollama на время обучения нужно выгрузить (ollama stop)."""
    if not cuda or not free_vram_bytes:
        return 'CUDA не подтверждена: обучение на CPU возможно только для моделей до 0.5–1.5B и очень малых наборов.'
    free = free_vram_bytes / 1024 ** 3
    if free >= 19:
        return 'Свободно {:.1f} ГБ VRAM: подходит база 7B (например, Qwen2.5-7B-Instruct, ~15 ГБ весов bf16). 14B без 4-битной загрузки не поместится.'.format(free)
    if free >= 9:
        return 'Свободно {:.1f} ГБ VRAM: подходит база 3B (~6.5 ГБ весов bf16). Для 7B выгрузите модели Ollama и закройте другие GPU-программы.'.format(free)
    if free >= 4:
        return 'Свободно {:.1f} ГБ VRAM: подходит база 1.5B.'.format(free)
    return 'Свободно {:.1f} ГБ VRAM: недостаточно для LoRA; освободите видеопамять.'.format(free)


def import_model(name, model_dir):
    """Explicit local Ollama import; preserve previously installed model names."""
    from local_agents import request_json
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*(?::[A-Za-z0-9][A-Za-z0-9_.-]*)?', str(name)) or 'cloud' in name.lower():
        raise ValueError('Задайте новое локальное имя модели (латиница, цифры, . _ - и необязательный тег).')
    executable = shutil.which('ollama')
    if not executable:
        raise ValueError('CLI Ollama не найден в PATH.')
    path = Path(model_dir).resolve()
    if not path.exists() or any(c in str(path) for c in '\r\n"'):
        raise ValueError('Путь не существует либо содержит неподдерживаемые символы.')
    if path.is_dir():
        if not (path / 'config.json').is_file() or not list(path.glob('*.safetensors')):
            raise ValueError('Нужна объединённая модель: config.json и веса Safetensors, не отдельный адаптер.')
    elif path.suffix.lower() != '.gguf':
        raise ValueError('Поддерживается папка Safetensors или файл GGUF.')
    endpoint = 'http://127.0.0.1:11434'
    canonical = name if ':' in name else name + ':latest'
    existing = request_json(endpoint, '/api/tags').get('models', [])
    if any(m.get('name') in (name, canonical) or m.get('model') in (name, canonical) for m in existing):
        raise ValueError('Модель с таким именем уже установлена. Используйте новое имя.')
    modelfile = path.parent / ('Modelfile-' + uuid.uuid4().hex)
    # Ollama accepts a quoted FROM absolute path; forward slashes work on Windows too.
    modelfile.write_text('FROM "' + path.as_posix() + '"\n', encoding='utf-8')
    try:
        proc = subprocess.run([executable, 'create', name, '-f', str(modelfile)],
                              env=_offline_env(), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=1800, shell=False, **hidden())
        if proc.returncode:
            raise ValueError('Ollama не смог импортировать архитектуру/веса: ' + (proc.stderr or proc.stdout)[-4000:])
        found = request_json(endpoint, '/api/show', {'model': name})
        if found.get('remote_host') or found.get('remote_model') or found.get('capabilities') == ['cloud']:
            raise ValueError('Импортированная модель не подтверждена как локальная.')
        names = request_json(endpoint, '/api/tags').get('models', [])
        if not any(m.get('name') in (name, canonical) or m.get('model') in (name, canonical) for m in names):
            raise ValueError('Имя отсутствует в локальном реестре после импорта.')
        return {'name': canonical, 'status': 'imported', 'source': str(path),
                'details': found.get('details', {}), 'log': (proc.stdout + proc.stderr)[-4000:]}
    finally:
        modelfile.unlink(missing_ok=True)
