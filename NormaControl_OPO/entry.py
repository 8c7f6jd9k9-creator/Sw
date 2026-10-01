"""Windows desktop entry: лицензия USB, целостность сборки, журнал сбоев, один экземпляр.

Вызывается из app_entry.py. В клиентской сборке модуль поставляется скомпилированным.
"""
import hashlib
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.append(str(BASE))  # в конце: файлы в папке программы не перекрывают стандартные модули
# Заполняются tools/build_release.py для клиентской сборки: SHA-256 скомпилированных модулей
# и допустимые исходные файлы. В исходном дереве разработчика проверка не выполняется.
BUILD_HASHES = {}
BUILD_SOURCES = []
CODE_SUFFIXES = ('.py', '.pyc', '.pyd', '.pyw', '.dll')
LICENSE_EXIT = 3
INTEGRITY_EXIT = 4


def log_folder():
    folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NormaControlOPO' / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def log_event(kind, text):
    try:
        path = log_folder() / '{}_{}.txt'.format(kind, datetime.now().strftime('%Y%m%d_%H%M%S'))
        path.write_text(text, encoding='utf-8')
        return path
    except OSError:
        return None


def integrity_problems():
    """Клиентская сборка: модули не подменены и не перекрыты исходными .py."""
    problems = []
    if not BUILD_HASHES:
        return problems
    for name, expected in BUILD_HASHES.items():
        path = BASE / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(name)
    allowed = set(BUILD_HASHES) | set(BUILD_SOURCES) | {'entry.pyc'}
    for path in sorted(BASE.iterdir()):
        if path.suffix.lower() in CODE_SUFFIXES and path.name not in allowed:
            problems.append(path.name + ' (посторонний файл)')
    return problems


def check_integrity():
    problems = integrity_problems()
    if problems:
        log_event('integrity', 'Изменены файлы программы: ' + ', '.join(problems))
        # Модули программы здесь не импортируются: они могли быть подменены.
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror('НормаКонтроль ОПО', 'Файлы программы изменены или повреждены: ' + ', '.join(problems[:5]) +
                                 '\nПереустановите программу из исходного архива.', parent=root)
            root.destroy()
        except Exception:
            pass
        return False
    return True


def license_or_exit():
    import usb_license
    status = usb_license.find_license()
    if not status.ok:
        log_event('license', 'Запуск без действительной лицензии. ' + status.reason)
        from license_ui import show_error
        show_error(status)
    return status


def license_status_report():
    import json
    import usb_license
    status = usb_license.find_license()
    drives = []
    try:
        drives = [{'drive': d.root, 'vendor': d.vendor, 'product': d.product, 'serial_present': bool(d.serial),
                   'license_file': (Path(d.root) / usb_license.LICENSE_FILE).is_file()} for d in usb_license.list_usb_drives()]
    except Exception as exc:
        drives = [{'error': str(exc)[:200]}]
    report = {'license': status.public(), 'usb_drives': drives}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status.ok else LICENSE_EXIT


def self_test():
    import json
    import sqlite3
    import tkinter
    import pypdf
    import pypdfium2  # noqa: F401
    import PIL
    import reportlab
    from app import App, VERSION  # noqa: F401
    from hardware import diagnose
    db = sqlite3.connect(':memory:')
    try:
        db.execute('CREATE VIRTUAL TABLE t USING fts5(x)')
        fts5 = 'ok'
    except sqlite3.OperationalError as exc:
        fts5 = 'error: ' + str(exc)
    finally:
        db.close()
    try:
        window = tkinter.Tk()
        window.withdraw()
        window.update()
        tk_window = 'ok; tk scaling {:.2f}'.format(float(window.tk.call('tk', 'scaling')))
        window.destroy()
    except Exception as exc:
        tk_window = 'error: ' + str(exc)
    import usb_license
    report = {'version': VERSION, 'license': usb_license.find_license().public(), 'python': sys.version, 'platform': sys.platform,
              'utf8_mode': bool(sys.flags.utf8_mode), 'sqlite': sqlite3.sqlite_version, 'fts5': fts5,
              'tk': tkinter.TkVersion, 'tk_window': tk_window, 'dpi_awareness': os.environ.get('NORMACONTROL_DPI', ''),
              'pypdf': pypdf.__version__, 'pillow': PIL.__version__, 'reportlab': reportlab.Version,
              'imports': 'ok', 'hardware': diagnose(BASE)}
    (BASE / 'Windows_self_test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if fts5 == 'ok' and tk_window.startswith('ok') else 1


def main():
    # Целостность — до импорта любых модулей программы.
    if not check_integrity():
        return INTEGRITY_EXIT
    from ui_scale import enable_windows_dpi_awareness
    # До создания первого окна Tk: чёткий текст при масштабе Windows 125–200 %.
    os.environ['NORMACONTROL_DPI'] = enable_windows_dpi_awareness()
    if '--self-test' in sys.argv:
        return self_test()
    if '--license-status' in sys.argv:
        return license_status_report()
    if not license_or_exit().ok:
        return LICENSE_EXIT
    if '--acceptance' in sys.argv:
        from acceptance import main as acceptance
        return acceptance([a for a in sys.argv[1:] if a != '--acceptance'])
    from app import App, data_root
    root = data_root(); root.mkdir(parents=True, exist_ok=True)
    lock = (root / 'desktop.lock').open('a+b')
    if sys.platform == 'win32':
        import msvcrt
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'НормаКонтроль ОПО уже запущен. Перейдите в открытое окно.', 'НормаКонтроль ОПО', 0x40)
            lock.close(); return 0
    try:
        from usb_license import LicenseRequired
        try:
            app = App()
        except LicenseRequired as exc:  # флешку вынули между проверками
            from license_ui import show_error
            show_error(exc.status)
            return LICENSE_EXIT
        if '--smoke-test' in sys.argv:
            app.after(1200, app.quit_app)
        app.mainloop()
        lost = getattr(app, 'license_lost_status', None)
        if lost is not None:
            from license_ui import show_error
            show_error(lost)
            return LICENSE_EXIT
    finally:
        lock.close()
    return 0


def run():
    try:
        return main()
    except SystemExit:
        raise
    except Exception:
        path = log_event('error', 'Python {} • utf8_mode={} • {}\n\n{}'.format(sys.version, sys.flags.utf8_mode, sys.executable, traceback.format_exc()))
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror('НормаКонтроль ОПО', 'Приложение не запустилось. Журнал ошибки:\n' + str(path))
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(run())
