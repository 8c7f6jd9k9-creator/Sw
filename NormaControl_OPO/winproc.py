"""Параметры дочерних процессов для оконного приложения Windows."""
import subprocess
import sys


def hidden():
    """Без всплывающего консольного окна (tesseract, nvidia-smi, ollama) при запуске из pythonw."""
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
