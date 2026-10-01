"""Сообщения о лицензии и контроль наличия флешки-ключа во время работы."""
import math
import time
import tkinter as tk
from tkinter import ttk

import usb_license

TITLE = 'НормаКонтроль ОПО — лицензия'
HELP = ('Программа работает только с USB-флешкой-ключом, на которой записан файл {} от издателя.\n'
        'Вставьте флешку и запустите программу снова. Копия файла на другой флешке не действует.').format(usb_license.LICENSE_FILE)


def message(status):
    return '{}\n\n{}'.format(status.reason, HELP)


class LicenseWatch:
    """Периодически проверяет ключ. Без ключа — предупреждение и закрытие через grace секунд.

    Записи базы сохраняются сразу при каждом действии, поэтому закрытие не теряет данных.
    """

    def __init__(self, root, on_expired, check=None, poll_ok_ms=15000, poll_missing_ms=3000, grace_seconds=60):
        self.root, self.on_expired = root, on_expired
        self.check = check or usb_license.find_license
        self.poll_ok_ms, self.poll_missing_ms, self.grace = poll_ok_ms, poll_missing_ms, grace_seconds
        self.missing_since = None
        self.window = None
        self.label = None
        self.after_id = root.after(poll_ok_ms, self.tick)

    def tick(self):
        self.after_id = None
        try:
            status = self.check()
        except Exception as exc:  # сбой опроса приравнивается к отсутствию ключа
            status = usb_license.Status(False, 'Ошибка проверки ключа: ' + str(exc)[:200])
        if status.ok:
            self.missing_since = None
            self._close_window()
            self.after_id = self.root.after(self.poll_ok_ms, self.tick)
            return
        now = time.monotonic()
        if self.missing_since is None:
            self.missing_since = now
        remaining = self.grace - (now - self.missing_since)
        if remaining <= 0:
            self._close_window()
            self.on_expired(status)
            return
        self._show(status, math.ceil(remaining))
        self.after_id = self.root.after(self.poll_missing_ms, self.tick)

    def _show(self, status, remaining):
        text = 'Флешка-ключ не обнаружена. Верните её в течение {} с, иначе программа закроется.\nВнесённые данные уже сохранены.\n\n{}'.format(remaining, status.reason)
        if self.window is None or not self.window.winfo_exists():
            self.window = tk.Toplevel(self.root)
            self.window.title(TITLE)
            self.window.attributes('-topmost', True)
            self.window.protocol('WM_DELETE_WINDOW', lambda: None)
            self.label = ttk.Label(self.window, text=text, padding=20, wraplength=520, justify='left')
            self.label.pack(fill='both', expand=True)
            self.window.update_idletasks()
            x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - self.window.winfo_reqwidth()) // 2)
            y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - self.window.winfo_reqheight()) // 3)
            self.window.geometry('+{}+{}'.format(x, y))
        else:
            self.label.configure(text=text)

    def _close_window(self):
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None

    def stop(self):
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        self._close_window()


def show_error(status):
    """Окно ошибки до запуска основного окна программы."""
    try:
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(TITLE, message(status), parent=root)
        root.destroy()
    except Exception:
        pass
