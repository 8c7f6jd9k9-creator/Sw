"""Приёмочная проверка на компьютере пользователя (Acceptance_Windows.cmd).

Работает на временной тестовой базе: рабочая база пользователя не открывается
и не изменяется. Отчёт (JSON + TXT) сохраняется в папке acceptance рядом с
программой. В отчёт не записываются серийные номера, UUID, имя компьютера и
имя пользователя (пути профиля заменяются на %USERPROFILE%).

    runtime\\python.exe -I -X utf8 app_entry.py --acceptance [--model qwen2.5:14b]
        [--photo C:\\фото.jpg] [--document C:\\документ.pdf] [--skip-gui] [--skip-ollama]
"""
import argparse
import difflib
import json
import os
import platform
import re
import shutil
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

QUERY = 'наряд-допуск газоопасные работы'
SITUATION = ('При проведении газоопасных работ в резервуаре не оформлен наряд-допуск, '
             'отсутствует анализ воздушной среды перед началом работ.')


def _redact(value):
    text = str(value)
    for key in ('USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP', 'HOME'):
        folder = os.environ.get(key)
        if folder and len(folder) > 3:
            text = text.replace(folder, '%' + key + '%')
    for key in ('USERNAME', 'COMPUTERNAME', 'USERDOMAIN'):
        name = os.environ.get(key)
        if name and len(name) > 2:
            text = re.sub(re.escape(name), '<' + key + '>', text, flags=re.IGNORECASE)
    return text


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return _redact(obj)


class Run:
    def __init__(self, args):
        from app import VERSION
        self.args = args
        self.started = datetime.now()
        self.report = {'product': 'НормаКонтроль ОПО', 'version': VERSION,
                       'started': self.started.isoformat(timespec='seconds'), 'steps': []}
        self.work = Path(tempfile.mkdtemp(prefix='NormaControl_acceptance_'))
        self.data = self.work / 'data'
        self.out = BASE / 'acceptance'
        try:
            self.out.mkdir(exist_ok=True)
            (self.out / '.write_test').write_text('ok', encoding='utf-8')
            (self.out / '.write_test').unlink()
        except OSError:  # папка программы только для чтения
            self.out = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NormaControlOPO' / 'acceptance'
            self.out.mkdir(parents=True, exist_ok=True)
        self.stamp = self.started.strftime('%Y%m%d_%H%M%S')

    def step(self, name, function):
        print('…', name, flush=True)
        begin = time.monotonic()
        entry = {'name': name}
        try:
            details = function()
            entry['status'] = 'skip' if isinstance(details, dict) and details.get('skipped') else 'ok'
            entry['details'] = details
        except Exception as exc:
            entry['status'] = 'fail'
            entry['error'] = '{}: {}'.format(type(exc).__name__, exc)
            entry['traceback'] = traceback.format_exc()[-4000:]
        entry['seconds'] = round(time.monotonic() - begin, 2)
        self.report['steps'].append(entry)
        print('   ', entry['status'].upper(), entry.get('error', ''), flush=True)
        return entry

    # --- шаги -------------------------------------------------------------
    def environment(self):
        import tkinter
        from hardware import diagnose
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE VIRTUAL TABLE t USING fts5(x)')
            fts5 = True
        except sqlite3.OperationalError:
            fts5 = False
        finally:
            db.close()
        modules = {}
        for name in ('pypdf', 'pypdfium2', 'PIL', 'reportlab'):
            module = __import__(name)
            modules[name] = getattr(module, '__version__', getattr(module, 'Version', 'ok'))
        info = {'python': sys.version.split()[0], 'executable': sys.executable, 'platform': platform.platform(),
                'utf8_mode': bool(sys.flags.utf8_mode), 'isolated': bool(sys.flags.isolated),
                'preferred_encoding': __import__('locale').getpreferredencoding(False),
                'sqlite': sqlite3.sqlite_version, 'fts5': fts5, 'tk': tkinter.TkVersion,
                'modules': modules, 'hardware': diagnose(BASE)}
        if not fts5:
            raise RuntimeError('SQLite без FTS5: поиск по базе знаний невозможен.')
        return info

    def real_data_untouched_before(self):
        from app import data_root
        self.real_db = data_root() / 'promcontrol.sqlite3'
        self.real_state = (self.real_db.stat().st_size, self.real_db.stat().st_mtime_ns) if self.real_db.is_file() else None
        return {'real_data_exists': self.real_state is not None, 'test_folder': str(self.work)}

    def seed(self):
        from core import Store
        from regulations import NormativeCatalog, EXCLUDED_ACTS
        from service_text import contains_brand
        os.environ['PROMCONTROL_DATA_DIR'] = str(self.data)
        begin = time.monotonic()
        store = Store(self.data, BASE / 'registry.json')
        catalog = NormativeCatalog(self.data)
        first = catalog.seed()
        catalog.authorize_uploaded_corpus()
        seconds = round(time.monotonic() - begin, 1)
        second = catalog.seed()
        with closing(sqlite3.connect(self.data / 'promcontrol.sqlite3')) as db, db:
            sources = db.execute('SELECT COUNT(*) FROM kb_sources').fetchone()[0]
            chunks = db.execute('SELECT COUNT(*) FROM kb_chunks').fetchone()[0]
            authorized = db.execute('SELECT COUNT(*) FROM kb_sources WHERE retrieval_authorized=1').fetchone()[0]
            brand = sum(contains_brand(r[0]) for r in db.execute('SELECT text FROM kb_chunks'))
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        records = catalog.records()
        store.close()
        result = {'first_seed_seconds': seconds, 'catalog_records': len(records), 'sources': sources, 'chunks': chunks,
                  'authorized_nd': authorized, 'service_text_chunks': brand, 'integrity': integrity,
                  'excluded_present': [r['act_id'] for r in records if r['act_id'] in EXCLUDED_ACTS],
                  'errors': first['errors'], 'second_seed_created': second['created'],
                  'second_seed_imported': second['local_texts_imported']}
        problems = []
        if first['errors']:
            problems.append('ошибки каталога')
        if brand:
            problems.append('служебные надписи в индексе')
        if integrity != 'ok' or result['excluded_present'] or second['created'] or second['local_texts_imported']:
            problems.append('целостность/исключённые акты/повторный импорт')
        if authorized < 19:
            problems.append('разрешено для поиска НД: {} из 19'.format(authorized))
        if problems:
            raise RuntimeError('; '.join(problems) + ' ' + json.dumps(result, ensure_ascii=False)[:1500])
        return result

    def search(self):
        from knowledge import KnowledgeBase
        kb = KnowledgeBase(self.data)
        found = kb.search(QUERY, limit=5, include_authorized=True)
        if not found:
            raise RuntimeError('Поиск по корпусу НД ничего не нашёл.')
        rows = []
        for item in found:
            path = kb.open_path(item['source_id'])
            rows.append({'ref': '[К{}-Ф{}]'.format(item['source_id'], item['id']), 'title': item['title'][:120],
                         'location': item['location'], 'original_exists': path.is_file(), 'original_type': path.suffix})
        if self.args.open_original:
            os.startfile(str(kb.open_path(found[0]['source_id'])))  # noqa: S606 — явная просьба пользователя
        return {'query': QUERY, 'results': rows}

    def _sample_photo(self):
        from PIL import Image, ImageDraw
        path = self.work / 'sample_photo.jpg'
        image = Image.new('RGB', (1600, 1000), (160, 170, 180))
        ImageDraw.Draw(image).rectangle((200, 200, 1400, 800), outline=(200, 30, 30), width=20)
        exif = Image.Exif()
        exif[0x0112] = 6
        image.save(path, quality=85, exif=exif.tobytes())
        return path

    def situation(self):
        from core import Store
        from pypdf import PdfReader
        from situations import CATEGORIES, SituationStore
        store = Store(self.data, BASE / 'registry.json')
        try:
            situations = SituationStore(self.data)
            sid = situations.save('Приёмка: газоопасные работы', 1, CATEGORIES[4], 'Тестовая площадка', SITUATION)
            photo = Path(self.args.photo) if self.args.photo else self._sample_photo()
            situations.attach(sid, photo)
            if self.args.document:
                situations.attach(sid, Path(self.args.document))
            matches = situations.analyze(sid)
            situations.decide(sid, 'medium', 'Приёмочная проверка', 'Тестовое решение: требуется проверка наряда-допуска.')
            pdf = self.work / 'situation.pdf'
            html_path = self.work / 'situation.html'
            situations.export_report(sid, pdf)
            situations.export_report(sid, html_path)
            reader = PdfReader(pdf)
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            images = sum(len(page.images) for page in reader.pages)
            shutil.copyfile(pdf, self.out / ('situation_' + self.stamp + '.pdf'))
        finally:
            store.close()
        reopened = SituationStore(self.data).get(sid)
        result = {'matches': len(matches), 'refs': ['[К{}-Ф{}]'.format(m['source_id'], m['id']) for m in matches],
                  'pdf_pages': len(reader.pages), 'pdf_images': images, 'pdf_cyrillic': 'НормаКонтроль' in text,
                  'pdf_copy': str(self.out / ('situation_' + self.stamp + '.pdf')),
                  'user_photo': bool(self.args.photo), 'user_document': bool(self.args.document),
                  'status_after_reopen': reopened['status'], 'matches_after_reopen': len(reopened['matches'])}
        if not matches or not images or not result['pdf_cyrillic'] or reopened['status'] != 'confirmed':
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result

    def backup(self):
        from core import Store, restore_backup
        store = Store(self.data, BASE / 'registry.json')
        try:
            target = self.work / 'backup' / 'NormaControl_backup.zip'
            target.parent.mkdir()
            created = store.backup(target)
        finally:
            store.close()
        restored = self.work / 'restored'
        checked = restore_backup(target, restored)
        copy = Store(restored, BASE / 'registry.json')
        try:
            situations = copy.db.execute('SELECT COUNT(*) FROM nc_situations').fetchone()[0]
        finally:
            copy.close()
        result = {'zip_mb': round(created['bytes'] / 1024 ** 2, 1), 'files': created['files'],
                  'missing_files': created['missing_files'], 'integrity': checked['integrity'],
                  'restored_counts': checked['counts'], 'restored_situations': situations}
        if created['missing_files'] or situations < 1:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result

    def gui(self):
        if self.args.skip_gui:
            return {'skipped': True, 'reason': '--skip-gui'}
        import tkinter as tk
        from app import App
        import ui_scale
        errors = []
        tk.Tk.report_callback_exception = lambda self_, exc, value, tb: errors.append('{}: {}'.format(exc.__name__, value))
        app = App()
        result = {}
        try:
            app.update()
            tabs = app.sections.tabs()
            for tab in tabs:
                app.sections.select(tab)
                app.update()
                time.sleep(0.2)
            scenario = self._gui_scenario(app)
            app.sections.select(tabs[0])
            app.update()
            area = ui_scale.work_area(app)
            result = {'tabs': len(tabs), 'window_state': app.window_state, 'geometry': app.winfo_geometry(),
                      'screen': [app.winfo_screenwidth(), app.winfo_screenheight()], 'work_area': list(area),
                      'dpi_factor': ui_scale.factor(app), 'tk_scaling': float(app.tk.call('tk', 'scaling')),
                      'dpi_awareness': os.environ.get('NORMACONTROL_DPI', ''), 'callback_errors': errors,
                      'scenario': scenario}
            fits = app.winfo_width() <= area[2] + 16 and app.winfo_height() <= area[3] + 16
            result['fits_work_area'] = fits
            try:
                from PIL import ImageGrab
                x, y = app.winfo_rootx(), app.winfo_rooty()
                shot = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()))
                shot_path = self.out / ('window_' + self.stamp + '.png')
                shot.save(shot_path)
                result['screenshot'] = str(shot_path)
            except Exception as exc:
                result['screenshot_error'] = str(exc)
        finally:
            app.quit_app()
        scenario = result.get('scenario') or {}
        if errors or result.get('tabs') != 8 or not result.get('fits_work_area') or not scenario.get('passed'):
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result

    @staticmethod
    def _gui_scenario(app):
        """Через виджеты: новая ситуация → сохранить → источники → решение → передать ИИ."""
        from situations import CATEGORIES, RISKS
        tab = app.situations
        app.sections.select(tab)
        tab.new()
        tab.title.set('Приёмка через интерфейс')
        tab.category.set(CATEGORIES[4])
        tab.description.insert('1.0', SITUATION)
        saved = tab.save()
        tab.analyze()
        deadline = time.monotonic() + 180
        while tab._busy and time.monotonic() < deadline:
            app.update()
            time.sleep(0.05)
        app.update()
        matches = len(tab._matches)
        tab.reviewer.set('Приёмочная проверка')
        tab.risk.set(RISKS['medium'])
        tab.editor.select(2)
        tab.decision.insert('1.0', 'Тестовое решение специалиста через интерфейс.')
        tab.decide(False)
        status = tab.backend.get(tab.current)['status']
        tab.to_agent()
        app.update()
        task = app.agents.task.get('1.0', 'end-1c')
        result = {'saved': saved, 'matches': matches, 'status_after_decision': status,
                  'agent_tab_selected': app.sections.select() == str(app.agents),
                  'agent_task_has_description': SITUATION[:40] in task, 'status_text': tab.status.get()[:200]}
        result['passed'] = bool(saved and matches and status == 'confirmed' and result['agent_tab_selected'] and result['agent_task_has_description'])
        return result

    def reopen(self):
        from core import Store
        from regulations import NormativeCatalog
        store = Store(self.data, BASE / 'registry.json')
        try:
            assets = len(store.assets())
            again = NormativeCatalog(self.data).seed()
        finally:
            store.close()
        with closing(sqlite3.connect(self.data / 'promcontrol.sqlite3')) as db, db:
            situations = db.execute('SELECT COUNT(*) FROM nc_situations').fetchone()[0]
        result = {'assets': assets, 'situations': situations, 'created_on_reopen': again['created'],
                  'imported_on_reopen': again['local_texts_imported']}
        if assets != 33 or situations < 1 or again['created'] or again['local_texts_imported']:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result

    def ocr(self):
        from knowledge import KnowledgeBase
        kb = KnowledgeBase(self.data)
        diagnostics = kb.diagnostics()
        if not diagnostics['tesseract'] or not diagnostics['rus_available']:
            return {'skipped': True, 'reason': 'Tesseract с языком rus не установлен', 'diagnostics': diagnostics}
        from PIL import Image, ImageDraw, ImageFont
        expected = 'Наряд-допуск на газоопасные работы оформлен 01.10.2026'
        image = Image.new('RGB', (2000, 220), 'white')
        ImageDraw.Draw(image).text((40, 60), expected, font=ImageFont.truetype(str(BASE / 'resources' / 'DejaVuSans.ttf'), 64), fill='black')
        path = self.work / 'ocr_rus.png'
        image.save(path)
        text = kb._ocr(path, 'rus+eng').strip()
        ratio = difflib.SequenceMatcher(None, ' '.join(text.split()), expected).ratio()
        return {'languages': diagnostics['ocr_languages'], 'recognized': text[:200], 'similarity': round(ratio, 3)}

    def _windows_connections(self, pids):
        if sys.platform != 'win32' or not pids:
            return []
        from winproc import hidden
        output = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30, **hidden()).stdout
        remote = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == 'TCP' and parts[-1] in pids:
                address = parts[2].rsplit(':', 1)[0].strip('[]')
                if address not in ('127.0.0.1', '::1', '0.0.0.0', '::', '*') and parts[3] in ('ESTABLISHED', 'SYN_SENT'):
                    remote.append({'pid': parts[-1], 'remote': parts[2], 'state': parts[3]})
        return remote

    def _ollama_pids(self):
        if sys.platform != 'win32':
            return set()
        from winproc import hidden
        output = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30, **hidden()).stdout
        pids = set()
        for line in output.splitlines():
            cells = [c.strip('"') for c in line.split('","')]
            if len(cells) > 1 and 'ollama' in cells[0].lower():
                pids.add(cells[1])
        return pids

    def ollama(self):
        if self.args.skip_ollama:
            return {'skipped': True, 'reason': '--skip-ollama'}
        from hardware import diagnose
        from local_agents import AgentService, check_local_metadata, request_json
        from core import Store
        from knowledge import KnowledgeBase
        endpoint = 'http://127.0.0.1:11434'
        try:
            version = request_json(endpoint, '/api/version')
        except ValueError as exc:
            return {'skipped': True, 'reason': 'Ollama не запущен на 127.0.0.1:11434: ' + str(exc)[:300]}
        names = sorted(m.get('name', '') for m in request_json(endpoint, '/api/tags').get('models', []))
        preferred = [self.args.model] if self.args.model else ['qwen2.5:14b', 'qwen2.5:7b']
        model = next((m for m in preferred if m in names), None) or (names[0] if names and not self.args.model else None)
        if not model:
            return {'skipped': True, 'reason': 'Модель не установлена', 'installed': names}
        info = request_json(endpoint, '/api/show', {'model': model})
        check_local_metadata(info)
        gpu_before = diagnose(BASE).get('gpu', [])
        pids = self._ollama_pids() | {str(os.getpid())}
        # 1) скорость: короткая генерация с метриками Ollama
        begin = time.monotonic()
        speed = request_json(endpoint, '/api/generate', {'model': model, 'stream': False, 'prompt': 'Перечисли три меры безопасности при газоопасных работах.',
                                                          'options': {'num_predict': 160, 'temperature': 0.2, 'num_ctx': 16384}})
        first_seconds = round(time.monotonic() - begin, 1)
        loaded = request_json(endpoint, '/api/ps').get('models', [])
        gpu_loaded = diagnose(BASE).get('gpu', [])
        eval_count, eval_ns = speed.get('eval_count') or 0, speed.get('eval_duration') or 0
        # 2) ответ роли с контекстом из корпуса и проверкой ссылок
        store = Store(self.data, BASE / 'registry.json')
        try:
            service = AgentService(store)
            service.save_settings(endpoint, model)
            context = KnowledgeBase(self.data).context(QUERY, limit=5, include_authorized=True)
            begin = time.monotonic()
            answer = service.run('regulatory', 'Какие требования к оформлению наряда-допуска на газоопасные работы? Укажи идентификаторы фрагментов.', context)
            answer_seconds = round(time.monotonic() - begin, 1)
        finally:
            store.close()
        connections = self._windows_connections(pids)
        provided = set(re.findall(r'\[К\d+-Ф\d+\]', context))
        cited = set(re.findall(r'\[К\d+-Ф\d+\]', answer))
        model_state = next((m for m in loaded if m.get('name') == model or m.get('model') == model), {})
        size, vram = model_state.get('size') or 0, model_state.get('size_vram') or 0
        result = {'ollama_version': version.get('version'), 'model': model, 'installed': names,
                  'model_details': info.get('details', {}),
                  'first_generation_seconds_including_load': first_seconds,
                  'tokens_per_second': round(eval_count / (eval_ns / 1e9), 1) if eval_ns else None,
                  'model_size_gib': round(size / 1024 ** 3, 2) if size else None,
                  'model_in_vram_percent': round(100 * vram / size, 1) if size else None,
                  'gpu_before': gpu_before, 'gpu_with_model_loaded': gpu_loaded,
                  'answer_seconds': answer_seconds, 'answer_chars': len(answer), 'answer_preview': answer[:1500],
                  'refs_provided': sorted(provided), 'refs_cited': sorted(cited),
                  'refs_cited_not_provided': sorted(cited - provided), 'citation_warning': '[ПРОВЕРКА ССЫЛОК' in answer,
                  'non_loopback_connections_of_app_and_ollama': connections,
                  'network_note': 'Снимок соединений TCP процессов программы и Ollama после генерации (netstat). Это свидетельство, а не полная проверка сети.'}
        (self.out / ('answer_' + self.stamp + '.txt')).write_text(answer, encoding='utf-8')
        return result

    def training(self):
        from training import TrainingStore
        return TrainingStore(self.work / 'training').diagnostics()

    def real_data_untouched_after(self):
        state = (self.real_db.stat().st_size, self.real_db.stat().st_mtime_ns) if self.real_db.is_file() else None
        if state != self.real_state:
            raise RuntimeError('Рабочая база изменилась во время проверки (возможно, программа была открыта).')
        return {'real_data_unchanged': True}

    def run(self):
        self.step('Окружение и зависимости', self.environment)
        self.step('Рабочая база не используется (до)', self.real_data_untouched_before)
        self.step('Первичная индексация корпуса НД', self.seed)
        self.step('Поиск по корпусу и оригиналы', self.search)
        self.step('Ситуация: фото/документ → источники → решение → PDF/HTML → повторное открытие', self.situation)
        self.step('Резервная копия, проверка и восстановление в отдельную папку', self.backup)
        self.step('Повторное открытие базы', self.reopen)
        self.step('Окно программы: вкладки, экран, масштаб', self.gui)
        self.step('OCR rus+eng', self.ocr)
        self.step('Локальная модель Ollama: ответ, ссылки, GPU, сеть', self.ollama)
        self.step('Диагностика обучения', self.training)
        self.step('Рабочая база не используется (после)', self.real_data_untouched_after)
        statuses = [s['status'] for s in self.report['steps']]
        self.report['summary'] = {'ok': statuses.count('ok'), 'fail': statuses.count('fail'), 'skip': statuses.count('skip'),
                                  'finished': datetime.now().isoformat(timespec='seconds')}
        report = _clean(self.report)
        json_path = self.out / ('Acceptance_report_' + self.stamp + '.json')
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['НормаКонтроль ОПО {} — приёмочная проверка {}'.format(report['version'], report['started']), '']
        for s in report['steps']:
            lines.append('[{}] {} ({} с){}'.format(s['status'].upper(), s['name'], s['seconds'], ': ' + s['error'] if s.get('error') else ''))
        lines += ['', 'Итог: OK {ok}, FAIL {fail}, SKIP {skip}'.format(**report['summary']),
                  'Полные сведения: ' + json_path.name,
                  'Проверка не подтверждает юридическую актуальность документов и промышленную готовность.']
        (self.out / ('Acceptance_report_' + self.stamp + '.txt')).write_text('\n'.join(lines), encoding='utf-8')
        print('\n'.join(lines), flush=True)
        if not self.args.keep:
            shutil.rmtree(self.work, ignore_errors=True)
        return 1 if report['summary']['fail'] else 0


def main(argv):
    parser = argparse.ArgumentParser(description='Приёмочная проверка НормаКонтроль ОПО')
    parser.add_argument('--model', help='имя локальной модели Ollama, например qwen2.5:14b')
    parser.add_argument('--photo', help='своя фотография для сценария ситуации')
    parser.add_argument('--document', help='свой документ (PDF/DOCX/TXT) для сценария ситуации')
    parser.add_argument('--skip-gui', action='store_true')
    parser.add_argument('--skip-ollama', action='store_true')
    parser.add_argument('--open-original', action='store_true', help='открыть найденный оригинал в Word')
    parser.add_argument('--keep', action='store_true', help='не удалять временную тестовую базу')
    args = parser.parse_args(argv)
    return Run(args).run()
