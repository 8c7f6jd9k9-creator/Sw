"""Local diagnostics; never submits hardware identifiers to a service."""
import ctypes
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def diagnose(root):
    result = {'system': platform.platform(), 'architecture': platform.machine(),
              'python': sys.version.split()[0], 'gpu': [], 'gpu_error': '',
              'free_disk_gib': round(shutil.disk_usage(root).free / 1024**3, 1)}
    if sys.platform == 'win32':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ('total_ram', 'free_ram', 'total_page', 'free_page', 'total_virtual', 'free_virtual', 'free_extended')]
        m = Memory(); m.length = ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            result.update(total_ram_gib=round(m.total_ram / 1024**3, 1), free_ram_gib=round(m.free_ram / 1024**3, 1))
    binary = shutil.which('nvidia-smi')
    if not binary and sys.platform == 'win32':
        candidates = [Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/nvidia-smi.exe',
                      Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'NVIDIA Corporation/NVSMI/nvidia-smi.exe']
        binary = next((str(p) for p in candidates if p.is_file()), None)
    if binary:
        try:
            p = subprocess.run([binary, '--query-gpu=name,memory.total,memory.free,driver_version', '--format=csv,noheader,nounits'],
                               capture_output=True, text=True, timeout=15, shell=False)
            if p.returncode:
                result['gpu_error'] = p.stderr.strip()[:1000]
            else:
                for line in p.stdout.splitlines():
                    fields = [x.strip() for x in line.split(',')]
                    if len(fields) == 4:
                        result['gpu'].append({'name': fields[0], 'total_vram_mib': fields[1], 'free_vram_mib': fields[2], 'driver': fields[3]})
        except (OSError, subprocess.TimeoutExpired) as exc:
            result['gpu_error'] = str(exc)
    else:
        result['gpu_error'] = 'nvidia-smi не найден. Доступность GPU не подтверждена.'
    return result
