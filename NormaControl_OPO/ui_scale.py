"""Размер окон по рабочей области экрана и масштабу Windows (100–200 %)."""
import ctypes
import sys
from tkinter import ttk


def enable_windows_dpi_awareness():
    """Вызывается до создания Tk: чёткий текст при масштабе 125–200 %.

    Шрифты Tk заданы в пунктах и масштабируются сами; размеры в пикселях
    приводятся функциями ниже. Ошибка API не мешает запуску.
    """
    if sys.platform != 'win32':
        return 'not_windows'
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
        return 'system'
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return 'legacy'
        except (AttributeError, OSError):
            return 'unavailable'


def factor(widget):
    """Отношение фактического DPI к 96 (1.0 при 100 %)."""
    try:
        return max(1.0, round(widget.winfo_fpixels('1i') / 96.0, 2))
    except Exception:
        return 1.0


def px(widget, value):
    return int(round(value * factor(widget)))


def work_area(widget):
    """Рабочая область без панели задач: (x, y, ширина, высота)."""
    if sys.platform == 'win32':
        try:
            from ctypes import wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except (AttributeError, OSError):
            pass
    return 0, 0, widget.winfo_screenwidth(), max(400, widget.winfo_screenheight() - 48)


def fit_window(win, width, height, min_width=None, min_height=None, maximize_if_small=False):
    """Задать размер окна в «логических» пикселях 96 DPI, не выходя за экран."""
    x0, y0, area_w, area_h = work_area(win)
    frame = px(win, 40)  # заголовок окна и рамки
    want_w, want_h = px(win, width), px(win, height)
    w, h = min(want_w, area_w - px(win, 8)), min(want_h, area_h - frame)
    if min_width and min_height:
        win.minsize(min(px(win, min_width), w), min(px(win, min_height), h))
    if maximize_if_small and (want_w > w or want_h > h) and sys.platform == 'win32':
        try:
            win.state('zoomed')
            return 'zoomed', w, h
        except Exception:
            pass
    win.geometry('{}x{}+{}+{}'.format(w, h, x0 + max(0, (area_w - w) // 2), y0 + max(0, (area_h - frame - h) // 2)))
    return 'normal', w, h


def scale_treeview_columns(root):
    """Ширины столбцов таблиц заданы в пикселях 96 DPI: масштабируются один раз."""
    f = factor(root)
    if f <= 1.05 or getattr(ttk.Treeview, '_normacontrol_scaled', False):
        return f
    original = ttk.Treeview.column

    def column(self, column, option=None, **kw):
        for key in ('width', 'minwidth'):
            if isinstance(kw.get(key), int):
                kw[key] = int(round(kw[key] * f))
        return original(self, column, option, **kw)

    ttk.Treeview.column = column
    ttk.Treeview._normacontrol_scaled = True
    return f


def responsive_wraplength(root, margin=24):
    """Подписи с фиксированным wraplength переносятся по ширине родителя.

    Иначе на узком экране длинная подпись уходит за правый край окна.
    """
    def visit(widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Label):
                try:
                    limit = int(str(child.cget('wraplength')) or 0)
                except (ValueError, TypeError):
                    limit = 0
                if limit > 0:
                    limit = px(child, limit)
                    child.configure(wraplength=limit)
                    parent = child.master

                    def update(event, label=child, maximum=limit, owner=parent):
                        if event.widget is not owner:
                            return
                        width = max(160, min(maximum, event.width - margin))
                        if int(str(label.cget('wraplength')) or 0) != width:
                            label.configure(wraplength=width)

                    parent.bind('<Configure>', update, add='+')
            visit(child)
    visit(root)
