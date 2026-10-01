"""Windows desktop entry, isolated imports, crash log and one local instance."""
import os
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def main():
    if '--self-test' in sys.argv:
        import json
        import tkinter
        import sqlite3
        import pypdf
        import pypdfium2
        import PIL
        import reportlab
        from app import App
        from hardware import diagnose
        report = {'python': sys.version, 'platform': sys.platform,
                  'sqlite': sqlite3.sqlite_version, 'tk': tkinter.TkVersion,
                  'pypdf': pypdf.__version__, 'pillow': PIL.__version__,
                  'reportlab': reportlab.Version, 'imports': 'ok', 'hardware': diagnose(BASE)}
        (BASE / 'Windows_self_test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return
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
            lock.close(); return
    try:
        app = App()
        if '--smoke-test' in sys.argv:
            app.after(1200, app.quit_app)
        app.mainloop()
    finally:
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        from datetime import datetime
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NormaControlOPO' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('error_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.txt')
        path.write_text(traceback.format_exc(), encoding='utf-8')
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror('НормаКонтроль ОПО', 'Приложение не запустилось. Журнал ошибки:\n' + str(path))
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
