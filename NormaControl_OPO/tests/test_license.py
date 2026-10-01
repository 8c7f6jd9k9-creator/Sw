"""Лицензия на USB-флешке: подпись Ed25519, привязка к накопителю, запуск и контроль во время работы."""
import json
import os
import tempfile
import time
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import nc_ed25519
import usb_license
from usb_license import Drive, LicenseRequired, find_license, require, sign_document

BASE = Path(__file__).resolve().parents[1]
SEED = bytes(range(32))
KEYS = {'test-key': nc_ed25519.public_key(SEED).hex()}


def payload(**changes):
    data = {'product': usb_license.PRODUCT, 'product_major': usb_license.PRODUCT_MAJOR, 'license_id': 'NC-TEST-1',
            'licensee': 'Тестовая организация', 'issued': '2026-01-01', 'expires': '',
            'device': {'bus': 'USB', 'vendor': 'Kingston', 'product': 'DataTraveler', 'serial': 'ABC123456', 'volume_serial': '1A2B3C4D'}}
    data.update(changes)
    return data


class Ed25519Tests(unittest.TestCase):
    def test_rfc8032_vectors(self):
        vectors = [
            ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60', 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
             'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
            ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb', '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
             '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
            ('c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7', 'fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025', 'af82',
             '6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a'),
        ]
        for seed, public, message, signature in vectors:
            seed, public, message, signature = map(bytes.fromhex, (seed, public, message, signature))
            self.assertEqual(nc_ed25519.public_key(seed), public)
            self.assertEqual(nc_ed25519.sign(seed, message), signature)
            self.assertTrue(nc_ed25519.verify(public, message, signature))
            self.assertFalse(nc_ed25519.verify(public, message + b'!', signature))
            broken = bytearray(signature)
            broken[5] ^= 1
            self.assertFalse(nc_ed25519.verify(public, message, bytes(broken)))

    def test_production_key_is_valid_point(self):
        key = bytes.fromhex(usb_license.PUBLIC_KEYS['nc-2026-1'])
        self.assertIsNotNone(nc_ed25519._decompress(key))


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def drive(self, name='E', serial='ABC123456', volume='1A2B3C4D', document=None, bus='USB'):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        if document is not None:
            (folder / usb_license.LICENSE_FILE).write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        return Drive(str(folder), bus, 'Kingston', 'DataTraveler', serial, volume)

    def test_valid_license_on_bound_drive(self):
        status = find_license([self.drive(document=sign_document(payload(), SEED, 'test-key'))], KEYS, date(2026, 10, 1))
        self.assertTrue(status.ok, status.reason)
        self.assertEqual(status.payload['licensee'], 'Тестовая организация')
        public = json.dumps(status.public(), ensure_ascii=False)
        self.assertNotIn('ABC123456', public)
        self.assertNotIn('1A2B3C4D', public)

    def test_copy_to_other_drive_or_reformatted_volume_rejected(self):
        document = sign_document(payload(), SEED, 'test-key')
        other = find_license([self.drive(serial='ZZZ999', document=document)], KEYS)
        self.assertFalse(other.ok)
        self.assertIn('другой флешки', other.reason)
        volume = find_license([self.drive(volume='FFFF0000', document=document)], KEYS)
        self.assertFalse(volume.ok)
        not_usb = find_license([self.drive(bus='SATA', document=document)], KEYS)
        self.assertFalse(not_usb.ok)

    def test_tampered_forged_and_foreign_licenses_rejected(self):
        document = sign_document(payload(), SEED, 'test-key')
        document['payload']['licensee'] = 'Другая организация'
        self.assertIn('подпись', find_license([self.drive(document=document)], KEYS).reason)
        forged = sign_document(payload(), bytes(32), 'test-key')
        self.assertFalse(find_license([self.drive(document=forged)], KEYS).ok)
        unknown = sign_document(payload(), SEED, 'other-key')
        self.assertFalse(find_license([self.drive(document=unknown)], KEYS).ok)
        # Подписано тестовым ключом: рабочие ключи программы его не принимают.
        self.assertFalse(find_license([self.drive(document=sign_document(payload(), SEED, 'nc-2026-1'))]).ok)
        other_product = sign_document(payload(product_major=2), SEED, 'test-key')
        self.assertIn('версии', find_license([self.drive(document=other_product)], KEYS).reason)

    def test_dates(self):
        expiring = sign_document(payload(expires='2026-12-31'), SEED, 'test-key')
        self.assertTrue(find_license([self.drive(document=expiring)], KEYS, date(2026, 12, 31)).ok)
        self.assertIn('истёк', find_license([self.drive(document=expiring)], KEYS, date(2027, 1, 1)).reason)
        future = sign_document(payload(issued='2027-01-01'), SEED, 'test-key')
        self.assertIn('начинает', find_license([self.drive(document=future)], KEYS, date(2026, 10, 1)).reason)

    def test_missing_corrupt_and_multiple_drives(self):
        self.assertIn('Вставьте флешку', find_license([], KEYS).reason)
        self.assertIn('нет файла', find_license([self.drive()], KEYS).reason)
        broken = self.drive('F')
        (Path(broken.root) / usb_license.LICENSE_FILE).write_text('{не json', encoding='utf-8')
        self.assertIn('не читается', find_license([broken], KEYS).reason)
        good = self.drive('G', document=sign_document(payload(), SEED, 'test-key'))
        status = find_license([broken, self.drive('H', serial='OTHER', document=sign_document(payload(), SEED, 'test-key')), good], KEYS)
        self.assertTrue(status.ok)
        self.assertEqual(status.drive, good.root)
        with self.assertRaises(LicenseRequired):
            require([broken], KEYS)

    def test_hex_encoded_serial_matches(self):
        hex_serial = 'ABC123456'.encode('ascii').hex().upper()
        status = find_license([self.drive(serial=hex_serial, document=sign_document(payload(), SEED, 'test-key'))], KEYS)
        self.assertTrue(status.ok, status.reason)

    def test_drive_listing_failure_is_reported_not_raised(self):
        with patch('usb_license.list_usb_drives', side_effect=OSError('нет доступа')):
            self.assertIn('Не удалось опросить', find_license(public_keys=KEYS).reason)

    def test_no_license_outside_windows(self):
        if os.name == 'nt':
            self.skipTest('Перечисление накопителей Windows проверяется на целевой машине')
        self.assertEqual(usb_license.list_usb_drives(), [])
        self.assertFalse(find_license().ok)


class EntryAndAppTests(unittest.TestCase):
    def test_app_refuses_without_license_before_window(self):
        import app
        with patch('usb_license.list_usb_drives', return_value=[]), patch.object(app.tk.Tk, '__init__') as window:
            with self.assertRaises(LicenseRequired):
                app.App()
            window.assert_not_called()

    def test_entry_exits_with_license_code_and_logs(self):
        import entry
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LOCALAPPDATA': tmp}), \
                patch('usb_license.list_usb_drives', return_value=[]), patch('license_ui.show_error') as shown, \
                patch.object(entry.sys, 'argv', ['app_entry.py']):
            self.assertEqual(entry.main(), entry.LICENSE_EXIT)
            shown.assert_called_once()
            logs = list((Path(tmp) / 'NormaControlOPO' / 'logs').glob('license_*.txt'))
            self.assertEqual(len(logs), 1)
            self.assertFalse((Path(tmp) / 'NormaControlOPO' / 'promcontrol.sqlite3').exists())

    def test_integrity_detects_modified_module_and_shadow_source(self):
        import entry
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / 'app.pyc'
            module.write_bytes(b'compiled')
            import hashlib
            (Path(tmp) / 'app_entry.py').write_text('# заглушка', encoding='utf-8')
            (Path(tmp) / 'registry.json').write_text('[]', encoding='utf-8')
            with patch.object(entry, 'BASE', Path(tmp)), patch.object(entry, 'BUILD_HASHES', {'app.pyc': hashlib.sha256(b'compiled').hexdigest()}), \
                    patch.object(entry, 'BUILD_SOURCES', ['app_entry.py']):
                self.assertEqual(entry.integrity_problems(), [])
                (Path(tmp) / 'app.py').write_text('# подмена', encoding='utf-8')
                self.assertEqual(entry.integrity_problems(), ['app.py (посторонний файл)'])
                (Path(tmp) / 'app.py').unlink()
                (Path(tmp) / 'hashlib.py').write_text('# подмена стандартного модуля', encoding='utf-8')
                self.assertEqual(entry.integrity_problems(), ['hashlib.py (посторонний файл)'])
                (Path(tmp) / 'hashlib.py').unlink()
                module.write_bytes(b'patched')
                self.assertEqual(entry.integrity_problems(), ['app.pyc'])
            self.assertEqual(entry.integrity_problems(), [])  # дерево разработчика: проверка не применяется


class WatchTests(unittest.TestCase):
    def setUp(self):
        try:
            self.tk = tk.Tk()
        except tk.TclError as exc:
            self.skipTest('Нет графического дисплея: ' + str(exc))
        self.tk.withdraw()

    def tearDown(self):
        self.tk.destroy()

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.tk.update()
            time.sleep(0.01)

    def test_removed_key_warns_then_closes_and_returning_key_cancels(self):
        from license_ui import LicenseWatch
        present = {'ok': True}
        expired = []
        check = lambda: usb_license.Status(present['ok'], 'нет ключа' if not present['ok'] else 'ok')
        watch = LicenseWatch(self.tk, expired.append, check, poll_ok_ms=20, poll_missing_ms=20, grace_seconds=0.4)
        present['ok'] = False
        self.pump(0.15)
        self.assertIsNotNone(watch.window)
        present['ok'] = True
        self.pump(0.15)
        self.assertIsNone(watch.window)
        self.assertEqual(expired, [])
        present['ok'] = False
        self.pump(0.8)
        self.assertEqual(len(expired), 1)
        watch.stop()


if __name__ == '__main__':
    unittest.main()
