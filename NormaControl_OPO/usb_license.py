"""Лицензия на USB-флешке: NormaControl.lic, подписанный Ed25519 и привязанный к накопителю.

Файл лежит в корне флешки. Подпись создаётся закрытым ключом издателя (его нет
в программе); программа содержит только открытые ключи. Лицензия действительна,
только если она прочитана с USB-накопителя, серийный номер устройства и серийный
номер тома которого совпадают с указанными в лицензии: копия файла на другую
флешку не работает, изменённый файл не проходит проверку подписи.

Серийные номера в отчёты и журналы программы не записываются.
"""
import base64
import ctypes
import json
import string
import struct
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import nc_ed25519

LICENSE_FILE = 'NormaControl.lic'
FORMAT = 'NormaControl-OPO-license-v1'
PRODUCT = 'НормаКонтроль ОПО'
PRODUCT_MAJOR = 1
CONTEXT = b'NormaControl-OPO-license-v1\n'
MAX_FILE = 64 * 1024
# Открытые ключи издателя лицензий. Закрытый ключ хранится только в комплекте издателя.
PUBLIC_KEYS = {
    'nc-2026-1': '597c9bcaab1a20c9854f46959e93dd6df9743a250b3c0a71e0a34494b85856b8',
}


@dataclass
class Drive:
    root: str
    bus: str
    vendor: str
    product: str
    serial: str
    volume_serial: str
    label: str = ''


@dataclass
class Status:
    ok: bool
    reason: str
    payload: dict = None
    drive: str = ''
    usb_drives: int = 0
    problems: list = field(default_factory=list)

    def public(self):
        """Сведения для отчётов и журналов — без серийных номеров накопителя."""
        payload = self.payload or {}
        return {'ok': self.ok, 'reason': self.reason, 'license_id': payload.get('license_id', ''),
                'licensee': payload.get('licensee', ''), 'issued': payload.get('issued', ''),
                'expires': payload.get('expires', '') or 'бессрочно' if payload else '',
                'drive': self.drive, 'usb_drives_found': self.usb_drives, 'problems': list(self.problems)}


class LicenseRequired(Exception):
    def __init__(self, status):
        super().__init__(status.reason)
        self.status = status


def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sign_document(payload, seed, key_id):
    signature = nc_ed25519.sign(seed, CONTEXT + canonical(payload))
    return {'format': FORMAT, 'key_id': key_id, 'payload': payload,
            'signature': base64.b64encode(signature).decode('ascii')}


def _serial_forms(value):
    """Одинаковый серийный номер в разных записях Windows (иногда в шестнадцатеричном виде)."""
    text = ''.join(str(value or '').split()).upper()
    forms = {text} if text else set()
    if text and len(text) % 2 == 0 and all(c in string.hexdigits for c in text):
        try:
            decoded = bytes.fromhex(text).decode('ascii')
            if decoded.isprintable() and decoded.strip():
                forms.add(''.join(decoded.split()).upper())
        except (ValueError, UnicodeDecodeError):
            pass
    return forms


def _parse_date(value):
    return date.fromisoformat(value) if value else None


def verify_document(document, drive, public_keys=None, today=None):
    """Проверка одного файла лицензии на конкретном накопителе: (True, '') или (False, причина)."""
    keys = PUBLIC_KEYS if public_keys is None else public_keys
    today = today or date.today()
    if not isinstance(document, dict) or document.get('format') != FORMAT:
        return False, 'неизвестный формат файла лицензии'
    payload = document.get('payload')
    key = keys.get(str(document.get('key_id', '')))
    if not isinstance(payload, dict) or not key or len(str(key)) != 64:
        return False, 'лицензия выдана не для этой программы'
    try:
        signature = base64.b64decode(str(document.get('signature', '')), validate=True)
        valid = nc_ed25519.verify(bytes.fromhex(key), CONTEXT + canonical(payload), signature)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        return False, 'подпись лицензии недействительна (файл изменён или выдан не для этой программы)'
    if payload.get('product') != PRODUCT or int(payload.get('product_major', -1)) != PRODUCT_MAJOR:
        return False, 'лицензия выдана для другой программы или версии'
    try:
        issued, expires = _parse_date(payload.get('issued', '')), _parse_date(payload.get('expires', ''))
    except ValueError:
        return False, 'в лицензии неверные даты'
    if issued and today < issued:
        return False, 'лицензия начинает действовать {:%d.%m.%Y}'.format(issued)
    if expires and today > expires:
        return False, 'срок лицензии истёк {:%d.%m.%Y}'.format(expires)
    device = payload.get('device') or {}
    if device.get('bus') != 'USB' or not _serial_forms(device.get('serial')):
        return False, 'в лицензии не указан USB-накопитель'
    same_serial = bool(_serial_forms(device.get('serial')) & _serial_forms(drive.serial))
    same_volume = not device.get('volume_serial') or str(device['volume_serial']).upper() == str(drive.volume_serial).upper()
    if drive.bus != 'USB' or not same_serial or not same_volume:
        return False, 'лицензия выдана для другой флешки (копия файла на другой накопитель не действует)'
    return True, ''


def find_license(drives=None, public_keys=None, today=None):
    """Найти действительную лицензию на подключённых USB-накопителях."""
    try:
        drives = list_usb_drives() if drives is None else list(drives)
    except Exception as exc:  # отказ API Windows не должен приводить к аварии
        return Status(False, 'Не удалось опросить USB-накопители: ' + str(exc)[:200])
    problems = []
    for drive in drives:
        path = Path(drive.root) / LICENSE_FILE
        try:
            if not path.is_file():
                continue
            if path.stat().st_size > MAX_FILE:
                problems.append('{}: файл лицензии слишком большой'.format(drive.root))
                continue
            document = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as exc:
            problems.append('{}: файл лицензии не читается ({})'.format(drive.root, type(exc).__name__))
            continue
        ok, reason = verify_document(document, drive, public_keys, today)
        if ok:
            return Status(True, 'Лицензия действительна.', document['payload'], drive.root, len(drives), problems)
        problems.append('{}: {}'.format(drive.root, reason))
    if not drives:
        reason = 'Не найден USB-накопитель с лицензией. Вставьте флешку-ключ НормаКонтроль ОПО.'
    elif not problems:
        reason = 'На подключённых USB-накопителях ({}) нет файла {}.'.format(len(drives), LICENSE_FILE)
    else:
        reason = 'Действительная лицензия не найдена: ' + '; '.join(problems)
    return Status(False, reason, None, '', len(drives), problems)


def require(drives=None, public_keys=None, today=None):
    status = find_license(drives, public_keys, today)
    if not status.ok:
        raise LicenseRequired(status)
    return status


# --- Windows: перечисление USB-накопителей ---------------------------------
_IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
_BUS_TYPE_USB = 7


def _kernel32():
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetLogicalDrives.restype = wintypes.DWORD
    k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    k32.GetDriveTypeW.restype = wintypes.UINT
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k32.DeviceIoControl.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                          ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    k32.GetVolumeInformationW.restype = wintypes.BOOL
    k32.SetErrorMode.argtypes = [wintypes.UINT]
    k32.SetErrorMode.restype = wintypes.UINT
    return k32, wintypes


def _storage_descriptor(k32, wintypes, letter):
    handle = k32.CreateFileW('\\\\.\\' + letter + ':', 0, 0x1 | 0x2, None, 3, 0, None)
    if handle in (None, 0, ctypes.c_void_p(-1).value):
        return None
    try:
        query = (ctypes.c_ulong * 3)(0, 0, 0)  # StorageDeviceProperty, PropertyStandardQuery
        buffer = ctypes.create_string_buffer(4096)
        returned = wintypes.DWORD(0)
        if not k32.DeviceIoControl(handle, _IOCTL_STORAGE_QUERY_PROPERTY, query, ctypes.sizeof(query),
                                   buffer, ctypes.sizeof(buffer), ctypes.byref(returned), None):
            return None
        raw = buffer.raw[:returned.value]
        if len(raw) < 36:
            return None
        fields = struct.unpack_from('<IIBBBBIIIII', raw, 0)
        vendor_offset, product_offset, serial_offset, bus = fields[6], fields[7], fields[9], fields[10]

        def text(offset):
            if not 0 < offset < len(raw):
                return ''
            return raw[offset:].split(b'\0', 1)[0].decode('ascii', 'replace').strip()

        return {'bus': bus, 'removable': bool(fields[4]), 'vendor': text(vendor_offset),
                'product': text(product_offset), 'serial': text(serial_offset)}
    finally:
        k32.CloseHandle(handle)


def _windows_usb_drives():
    k32, wintypes = _kernel32()
    previous = k32.SetErrorMode(0x0001 | 0x8000)  # без системных окон «вставьте диск»
    drives = []
    try:
        mask = k32.GetLogicalDrives()
        for index, letter in enumerate(string.ascii_uppercase):
            if not mask & (1 << index) or letter in 'AB':
                continue
            root = letter + ':\\'
            if k32.GetDriveTypeW(root) not in (2, 3):  # съёмный или «фиксированный» USB-диск
                continue
            try:
                info = _storage_descriptor(k32, wintypes, letter)
            except OSError:
                info = None
            if not info or info['bus'] != _BUS_TYPE_USB:
                continue
            serial = wintypes.DWORD(0)
            label = ctypes.create_unicode_buffer(261)
            if not k32.GetVolumeInformationW(root, label, 261, ctypes.byref(serial), None, None, None, 0):
                continue  # нет носителя
            drives.append(Drive(root, 'USB', info['vendor'], info['product'], info['serial'],
                                '{:08X}'.format(serial.value), label.value))
    finally:
        k32.SetErrorMode(previous)
    return drives


def list_usb_drives():
    """USB-накопители с файловой системой. Вне Windows ключ не поддерживается."""
    if sys.platform != 'win32':
        return []
    return _windows_usb_drives()
