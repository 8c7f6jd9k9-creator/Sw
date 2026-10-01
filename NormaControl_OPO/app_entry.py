"""Windows desktop entry, isolated imports, crash log and one local instance."""
import os
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


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
    report = {'version': VERSION, 'python': sys.version, 'platform': sys.platform,
              'utf8_mode': bool(sys.flags.utf8_mode), 'sqlite': sqlite3.sqlite_version, 'fts5': fts5,
              'tk': tkinter.TkVersion, 'tk_window': tk_window, 'dpi_awareness': os.environ.get('NORMACONTROL_DPI', ''),
              'pypdf': pypdf.__version__, 'pillow': PIL.__version__, 'reportlab': reportlab.Version,
              'imports': 'ok', 'hardware': diagnose(BASE)}
    (BASE / 'Windows_self_test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if fts5 == 'ok' and tk_window.startswith('ok') else 1


def main():
    from ui_scale import enable_windows_dpi_awareness
    # До создания первого окна Tk: чёткий текст при масштабе Windows 125–200 %.
    os.environ['NORMACONTROL_DPI'] = enable_windows_dpi_awareness()
    if '--self-test' in sys.argv:
        return self_test()
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
        app = App()
        if '--smoke-test' in sys.argv:
            app.after(1200, app.quit_app)
        app.mainloop()
    finally:
        lock.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        from datetime import datetime
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NormaControlOPO' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('error_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.txt')
        path.write_text('Python {} • utf8_mode={} • {}\n\n{}'.format(sys.version, sys.flags.utf8_mode, sys.executable, traceback.format_exc()), encoding='utf-8')
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror('НормаКонтроль ОПО', 'Приложение не запустилось. Журнал ошибки:\n' + str(path))
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
