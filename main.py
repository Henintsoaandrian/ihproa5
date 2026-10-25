import sys
import os
import time
import sqlite3
import tempfile
import json
import ssl
import certifi
import urllib.request
import urllib.parse
import threading
import platform
import hashlib

# =====================================================
# PATCH ROBUSTE pour construct_typed vs construct_typing
# =====================================================
try:
    import construct_typing
    sys.modules['construct_typed'] = construct_typing
except ImportError:
    try:
        import construct_typed
    except ImportError:
        print("Erreur: ni construct_typing ni construct_typed n'est installé.")
        sys.exit(1)
# =====================================================

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox, QDialog, QProgressBar, QCheckBox
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import (
    QPixmap, QIcon, QPainter, QColor, QFont, QPainterPath,
    QPen, QBrush
)

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService
from pymobiledevice3.services.diagnostics import DiagnosticsService

# ========================== CONSTANTS ==========================
BACKEND_URL        = 'http://api.mobidocserver.com/iHPro_Tool_A5/A5/server.php'
VALIDATE_URL       = 'https://api.mobidocserver.com/iHPro_Tool_A5/A5/validate.php'
TELEGRAM_URL       = 'https://api.mobidocserver.com/iHPro_Tool_A5/A5/telegramreport.php'
TELEGRAM_BOT_TOKEN = '8878915882:AAHcLQFjNsEmhO8gOQ6cT4ioC9S9iualdVs'
TELEGRAM_CHAT_ID   = '1913084477'
BACKEND_CACHE_TTL = 60 * 60 * 12
CACHE_DIR = os.path.join(os.path.expanduser('~'), '.ihproa5_cache')

OS_NAME = 'Windows' if sys.platform == 'win32' else ('macOS' if sys.platform == 'darwin' else 'Linux')

SUPPORTED = {
    'iPhone4,1': {'9.3.5', '9.3.6'},
    'iPad2,1':   {'8.4.1', '9.3.5'},
    'iPad2,2':   {'9.3.5', '9.3.6'},
    'iPad2,3':   {'9.3.5', '9.3.6'},
    'iPad2,4':   {'8.4.1', '9.3.5'},
    'iPad2,5':   {'8.4.1', '9.3.5'},
    'iPad2,6':   {'9.3.5', '9.3.6'},
    'iPad2,7':   {'9.3.5', '9.3.6'},
    'iPad3,1':   {'8.4.1', '9.3.5'},
    'iPad3,2':   {'9.3.5', '9.3.6'},
    'iPad3,3':   {'9.3.5', '9.3.6'},
    'iPod5,1':   {'8.4.1', '9.3.5'},
    'iPhone5,1': {'10.3.3', '10.3.4'},
    'iPhone5,2': {'10.3.3', '10.3.4'},
    'iPhone5,3': {'10.3.3', '10.3.4'},
    'iPhone5,4': {'10.3.3', '10.3.4'},
    'iPhone6,1': {'12.5.7', '12.5.8'},
    'iPad3,4':   {'10.3.3', '10.3.4'},
    'iPad3,5':   {'10.3.3', '10.3.4'},
    'iPad3,6':   {'10.3.3', '10.3.4'},
}

# ========================== UTILITY FUNCTIONS ==========================
def resource_path(name):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, name)


def _cache_file_for_key(prefix: str, key: str) -> str:
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)
    safe_key = hashlib.sha256(key.encode('utf-8', 'ignore')).hexdigest()
    return os.path.join(CACHE_DIR, f'{prefix}_{safe_key}.json')


def _read_backend_cache(prefix: str, key: str):
    try:
        path = _cache_file_for_key(prefix, key)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        expires_at = data.get('expires_at', 0)
        if expires_at and time.time() > expires_at:
            try:
                os.remove(path)
            except Exception:
                pass
            return None
        return data.get('value')
    except Exception:
        return None


def _write_backend_cache(prefix: str, key: str, value, ttl_seconds=BACKEND_CACHE_TTL):
    try:
        path = _cache_file_for_key(prefix, key)
        payload = {
            'value': value,
            'expires_at': time.time() + ttl_seconds,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
    except Exception:
        pass


def mask(value: str, visible: int = 4) -> str:
    if not value or len(value) <= visible:
        return value
    return value[:visible] + '****'


def send_telegram_report(device_info: dict, status: str):
    try:
        product = device_info.get('product', 'N/A')
        version = device_info.get('version', 'N/A')
        udid    = device_info.get('udid',    'N/A')
        imei    = device_info.get('imei',    'N/A')
        sn      = device_info.get('sn',      'N/A')

        ctx = ssl.create_default_context(cafile=certifi.where())

        try:
            geo_req = urllib.request.urlopen('http://ip-api.com/json/', timeout=5)
            geo     = json.loads(geo_req.read().decode())
            country = geo.get('country', 'Unknown')
            city    = geo.get('city', '')
            location = f'{city}, {country}' if city else country
        except Exception:
            location = 'Unknown'

        data = urllib.parse.urlencode({
            'status':   status,
            'product':  product,
            'sn':       sn,
            'imei':     imei,
            'version':  version,
            'udid':     udid,
            'os':       OS_NAME,
            'location': location,
        }).encode()

        urllib.request.urlopen(
            urllib.request.Request(TELEGRAM_URL, data=data, method='POST'),
            timeout=10,
            context=ctx
        )
    except Exception:
        pass


def report_async(device_info: dict, status: str):
    threading.Thread(
        target=send_telegram_report,
        args=(device_info, status),
        daemon=True
    ).start()


def build_db_from_sql(sql_path, backend_url, target_path):
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    sql = sql.replace('BACKEND_URL', backend_url).replace('TARGET_PATH', target_path)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        con = sqlite3.connect(tmp.name)
        con.executescript(sql)
        con.commit()
        con.close()
        with open(tmp.name, 'rb') as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass


def check_sn_registered(sn):
    if not sn:
        return False

    cache_key = f'validate:{sn}'
    cached = _read_backend_cache('sn_validation', cache_key)
    if cached is not None:
        return bool(cached)

    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        url = f'{VALIDATE_URL}?sn={sn}'
        req = urllib.request.urlopen(url, timeout=10, context=ctx)
        data = json.loads(req.read().decode())
        valid = bool(data.get('valid', False))
        _write_backend_cache('sn_validation', cache_key, valid, ttl_seconds=BACKEND_CACHE_TTL)
        return valid
    except Exception:
        return False

# ========================== CLICKABLE LABEL ==========================
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ========================== WIFI ICON (dessinée) ==========================
class WifiIcon(QLabel):
    def __init__(self, parent=None, size=48):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = QColor('#004ec5')
        pen = QPen(color)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        rect = self.rect()
        center = rect.center()

        max_r = min(rect.width(), rect.height()) // 2 - 4
        radii = [max_r // 3, max_r * 2 // 3, max_r - 2]

        start_angle = 45 * 16
        span_angle = 90 * 16

        for r in radii:
            painter.drawArc(
                center.x() - r,
                center.y() - r,
                r * 2,
                r * 2,
                start_angle,
                span_angle
            )

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 4, 4)

# ========================== SUCCESS DIALOG ==========================
class SuccessDialog(QDialog):
    def __init__(self, parent=None, device_info=None):
        super().__init__(parent)
        self.device_info = device_info or {}
        self.setWindowTitle('Dhmf Software Bypass A5-A6 Tool V1.0')
        self.setFixedSize(400, 150)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #adb3bd;
            }
            QLabel {
                color: #1e1e2f;
                border: none;
                background: transparent;
            }
            QPushButton {
                background-color: #004ec5;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0066ff;
            }
            QPushButton:pressed {
                background-color: #003399;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_lbl.setStyleSheet('border: none; background: transparent;')
        logo_path = resource_path('logo.png')
        if os.path.exists(logo_path):
            src = QPixmap(logo_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pix = QPixmap(64, 64)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 64, 64, 14, 14)
            p.setClipPath(path)
            p.drawPixmap(0, 0, src)
            p.end()
        else:
            pix = QPixmap(64, 64)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0, 0, 64, 64)
            p.setClipPath(path)
            p.fillRect(0, 0, 64, 64, QColor('#004ec5'))
            p.setPen(QColor('white'))
            p.setFont(QFont('Arial', 18, QFont.Bold))
            p.drawText(pix.rect(), Qt.AlignCenter, 'D')
            p.end()
        icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)

        right = QVBoxLayout()
        right.setSpacing(6)

        product = self.device_info.get('product', '')
        version = self.device_info.get('version', '')

        title = QLabel('Dhmf Software Bypass A5-A6 Tool V1.0')
        title.setStyleSheet(
            'font-size: 14px; font-weight: bold; color: #004ec5;'
            'border: none; background: transparent;'
        )

        msg = QLabel(f'Your Device {product} iOS {version}\nhas been Activated Successfully! 🎉')
        msg.setStyleSheet(
            'font-size: 12px; color: #1e1e2f;'
            'border: none; background: transparent;'
        )
        msg.setWordWrap(True)

        ok_btn = QPushButton('Ok')
        ok_btn.setFixedWidth(70)
        ok_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)

        right.addWidget(title)
        right.addWidget(msg)
        right.addLayout(btn_row)
        layout.addLayout(right)

# ========================== WIFI CONFIRMATION DIALOG (ENGLISH, WITH DRAWN ICON) ==========================
class WifiConfirmationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Wi-Fi Confirmation')
        self.setFixedSize(420, 210)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #ffffff;
                border-radius: 12px;
                border: 1px solid #adb3bd;
            }
            QLabel {
                color: #1e1e2f;
                background: transparent;
                border: none;
            }
            QPushButton {
                background-color: #004ec5;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0066ff;
            }
            QPushButton:disabled {
                background-color: #adb3bd;
                color: #666;
            }
            QPushButton#cancelBtn {
                background-color: #e8edf3;
                color: #4a5a6a;
            }
            QPushButton#cancelBtn:hover {
                background-color: #d0d8e0;
            }
            QCheckBox {
                color: #1e2a3a;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        # --- Icône Wi‑Fi dessinée ---
        wifi_icon = WifiIcon(self, size=48)
        layout.addWidget(wifi_icon, alignment=Qt.AlignCenter)

        title = QLabel('Connect your device to Wi-Fi')
        title.setStyleSheet('font-size: 14px; font-weight: bold;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(
            'Before starting the activation, please ensure:\n'
            '• Your iPhone/iPad is connected to a Wi-Fi network\n'
            '• The device is unlocked (screen on)\n'
            '• The USB cable is properly connected'
        )
        msg.setStyleSheet('font-size: 12px; color: #5a6a7a;')
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.checkbox = QCheckBox('I have connected my device to Wi-Fi')
        self.checkbox.setStyleSheet('font-size: 13px;')
        layout.addWidget(self.checkbox)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setObjectName('cancelBtn')
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.confirm_btn = QPushButton('Continue')
        self.confirm_btn.setFixedWidth(80)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.confirm_btn)

        layout.addLayout(btn_layout)

        self.checkbox.stateChanged.connect(self._on_checkbox_changed)

    def _on_checkbox_changed(self, state):
        self.confirm_btn.setEnabled(state == Qt.Checked)

# ========================== ACTIVATION THREAD ==========================
class ActivationThread(QThread):
    status  = pyqtSignal(str)
    success = pyqtSignal(str)
    error   = pyqtSignal(str)
    waiting = pyqtSignal(bool)

    def __init__(self, device_info=None):
        super().__init__()
        self._device_info = device_info or {}

    def wait_for_device(self, timeout=160):
        deadline = time.monotonic() + timeout
        first    = True
        while time.monotonic() < deadline:
            try:
                lockdown = create_using_usbmux()
                DiagnosticsService(lockdown=lockdown).mobilegestalt(keys=['ProductType'])
                if not first:
                    self.waiting.emit(False)
                    self.status.emit('Device reconnected ✓')
                return lockdown
            except Exception:
                if first:
                    self.waiting.emit(True)
                    self.status.emit('Waiting for device reconnection...')
                    first = False
                time.sleep(2)
        raise TimeoutError()

    def push_payload(self, lockdown, payload_db):
        with AfcService(lockdown=lockdown) as afc:
            try:
                for filename in afc.listdir('Downloads'):
                    try:
                        afc.rm('Downloads/' + filename)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(3)
            afc.set_file_contents('Downloads/downloads.28.sqlitedb', payload_db)
        DiagnosticsService(lockdown=lockdown).restart()
        return self.wait_for_device()

    def should_hactivate(self, lockdown):
        try:
            return DiagnosticsService(lockdown=lockdown).mobilegestalt(
                keys=['ShouldHactivate']
            ).get('ShouldHactivate', False)
        except:
            return False

    def run(self):
        try:
            lockdown = create_using_usbmux()
            values   = lockdown.get_value()

            # Suppression du test préliminaire – on lance toujours l'activation
            sql_path = resource_path('payload.sql')
            if not os.path.exists(sql_path):
                self.error.emit(f'Payload file not found: {sql_path}')
                return

            if tuple(int(x) for x in values.get('ProductVersion', '0.0').split('.')) >= (10, 3):
                payload_db = build_db_from_sql(
                    sql_path, BACKEND_URL,
                    '/private/var/containers/Shared/SystemGroup/'
                    'systemgroup.com.apple.mobilegestaltcache/Library/Caches/'
                    'com.apple.MobileGestalt.plist'
                )
            else:
                payload_db = build_db_from_sql(
                    sql_path, BACKEND_URL,
                    '/private/var/mobile/Library/Caches/com.apple.MobileGestalt.plist'
                )

            self.status.emit('Activating device...')

            for attempt in range(5):
                lockdown = self.push_payload(lockdown, payload_db)
                delay = 15 + attempt * 5
                time.sleep(delay)

                if self.should_hactivate(lockdown):
                    DiagnosticsService(lockdown=lockdown).restart()
                    report_async(self._device_info, 'Activated ✅')
                    self.success.emit('Done!')
                    return

                self.status.emit(f'Retrying activation — Attempt {attempt + 1}/5')
                time.sleep(5)

            report_async(self._device_info, 'Activation Failed ❌')
            self.error.emit(
                'Activation failed after multiple attempts. '
                'Make sure the device is connected to the Wi-Fi.'
            )

        except TimeoutError:
            report_async(self._device_info, 'Timeout Error ⏱️')
            self.error.emit(
                'Device did not reconnect in time. '
                'Please ensure it is connected and try again.'
            )
        except Exception as e:
            report_async(self._device_info, f'Exception ❌: {str(e)}')
            self.error.emit(str(e))

# ========================== MAIN WINDOW ==========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Dhmf Software Bypass A5-A6 Tool V1.0')
        self.setFixedSize(500, 330)
        self.setContentsMargins(0, 0, 0, 0)

        # Logo comme icône
        logo_path = resource_path('logo.png')
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # Variables d'état
        self._device_info    = {}
        self._current_sn     = ''
        self._reported_udids = set()

        # Widgets
        self.status = QLabel('No device connected', self)
        self.status.setObjectName("statusLabel")
        self.status.setAlignment(Qt.AlignCenter)

        self.lbl_uuid   = QLabel('', self)
        self.lbl_device = QLabel('', self)
        self.lbl_udid   = QLabel('', self)
        self.lbl_imei   = QLabel('', self)
        self.lbl_sn     = ClickableLabel('', self)
        self.lbl_sn.clicked.connect(self._copy_sn)
        self.lbl_sn.setToolTip('Click to copy Serial Number')

        for lbl in (self.lbl_uuid, self.lbl_device, self.lbl_udid, self.lbl_imei, self.lbl_sn, self.status):
            lbl.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        # Bouton Activate
        self.activate = QPushButton('Activate Device', self)
        self.activate.setEnabled(False)
        self.activate.setStyleSheet("""
            QPushButton {
                background-color: #adb3bd;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9aa3b0;
            }
            QPushButton:disabled {
                background-color: #c0c6d0;
                color: #666;
            }
        """)

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self.lbl_uuid)
        layout.addWidget(self.lbl_device)
        layout.addWidget(self.lbl_udid)
        layout.addWidget(self.lbl_imei)
        layout.addWidget(self.lbl_sn)
        layout.addSpacing(8)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.activate)

        central = QWidget(self)
        central.setLayout(layout)
        central.setGeometry(0, 0, 500, 330)
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        central.setAttribute(Qt.WA_TranslucentBackground)

        # Style global
        self.setStyleSheet("""
            QMainWindow { background: #f0f4f8; }
            QLabel { background-color: rgba(255,255,255,0.75); border-radius: 4px; padding: 2px 4px; }
            QLabel#statusLabel { color: #004ec5; font-weight: bold; background-color: rgba(255,255,255,0.85); }
            QProgressBar {
                border: 1px solid #adb3bd;
                border-radius: 6px;
                background: rgba(248,249,250,0.8);
                height: 16px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #004ec5;
                border-radius: 6px;
            }
        """)

        # Connexions
        self.activate.clicked.connect(self.start_activation)

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_val = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_device)
        self.timer.start(1000)

    # ---------- Copy SN ----------
    def _copy_sn(self):
        if self._current_sn:
            QApplication.clipboard().setText(self._current_sn)
            self.lbl_sn.setStyleSheet('color: #004ec5; background-color: rgba(255,255,255,0.75);')
            QTimer.singleShot(1000, lambda: self.lbl_sn.setStyleSheet('background-color: rgba(255,255,255,0.75);'))

    # ---------- Device polling ----------
    def poll_device(self):
        try:
            lockdown = create_using_usbmux()
            values   = lockdown.get_value()

            product = values.get('ProductType', '')
            version = values.get('ProductVersion', '')
            udid    = lockdown.udid or ''
            imei    = values.get('InternationalMobileEquipmentIdentity', '')
            sn      = values.get('SerialNumber', '')

            try:
                diag     = DiagnosticsService(lockdown=lockdown)
                mg       = diag.mobilegestalt(keys=['UniqueDeviceID'])
                app_uuid = mg.get('UniqueDeviceID', '') or udid
            except Exception:
                app_uuid = udid

            # ECID en décimal
            try:
                chip_id = lockdown.get_value(key='UniqueChipID')
                if isinstance(chip_id, int):
                    ecid = str(chip_id)
                else:
                    ecid = str(chip_id)
            except Exception:
                ecid = udid

            is_supported = SUPPORTED.get(product)
            if not is_supported:
                self._clear_info()
                self._set_state(f'Unsupported Device: {product}', False)
                return

            if version not in is_supported:
                self._clear_info()
                self._set_state(f'Unsupported {product} iOS version: {version}', False)
                return

            self._device_info = {
                'product': product,
                'version': version,
                'udid':    udid,
                'imei':    imei,
                'sn':      sn,
                'ecid':    ecid,
            }
            self._current_sn = sn

            if udid and udid not in self._reported_udids:
                self._reported_udids.add(udid)
                report_async(self._device_info, 'Device Connected 🔌')

            self.lbl_uuid.setText(f'APP_UUID: {app_uuid}')
            self.lbl_device.setText(f'Device: {product}  iOS {version}')
            self.lbl_udid.setText(f'ECID: {ecid}')
            self.lbl_imei.setText(f'IMEI: {imei}')
            self.lbl_sn.setText(f'Serial Number: {sn}  (click to copy)')
            self.status.setVisible(False)
            self.activate.setEnabled(True)

        except Exception:
            self._clear_info()
            self._set_state('No device connected', False)

    def _clear_info(self):
        self._device_info = {}
        self._current_sn  = ''
        self.lbl_uuid.setText('')
        self.lbl_device.setText('')
        self.lbl_udid.setText('')
        self.lbl_imei.setText('')
        self.lbl_sn.setText('')

    def _set_state(self, text, enabled):
        self.status.setText(text)
        self.status.setVisible(True)
        self.activate.setEnabled(enabled)

    # ---------- Progress simulation ----------
    def _tick_progress(self):
        if self._progress_val < 90:
            self._progress_val += 2
            self.progress.setValue(self._progress_val)

    def _on_activation_status(self, msg):
        self.status.setText(msg)

    def _on_waiting(self, waiting: bool):
        if waiting:
            self._progress_timer.stop()
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(self._progress_val)
            self._progress_timer.start(600)

    # ---------- Start activation ----------
    def start_activation(self):
        product = self._device_info.get('product', '')
        version = self._device_info.get('version', '')

        if product not in SUPPORTED or version not in SUPPORTED.get(product, set()):
            msg = QMessageBox(self)
            msg.setWindowTitle('Not Supported')
            msg.setText(f'Device {product} iOS {version} is not supported.')
            msg.setIcon(QMessageBox.Critical)
            msg.exec_()
            return

        # --- Wi-Fi confirmation dialog (English) ---
        wifi_dlg = WifiConfirmationDialog(self)
        if wifi_dlg.exec_() != QDialog.Accepted:
            self.status.setText('Activation cancelled')
            self.status.setVisible(True)
            return

        self.status.setText('Checking SN...')
        self.status.setVisible(True)
        QApplication.processEvents()

        if not check_sn_registered(self._current_sn):
            dlg = QDialog(self)
            dlg.setWindowTitle('Device Supported')
            dlg.setFixedWidth(380)
            dlg.setStyleSheet("""
                QDialog {
                    background: #ffffff;
                    border: 1px solid #adb3bd;
                    border-radius: 10px;
                }
                QLabel {
                    color: #1e1e2f;
                }
                QPushButton {
                    background-color: #004ec5;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 6px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0066ff;
                }
            """)
            dlg_layout = QVBoxLayout(dlg)
            dlg_layout.setContentsMargins(24, 24, 24, 20)
            dlg_layout.setSpacing(10)

            lbl_title = QLabel(f'✅ Device {product} iOS {version} is supported!')
            lbl_title.setStyleSheet('font-size: 13px; font-weight: bold; color: #004ec5;')
            lbl_title.setWordWrap(True)

            lbl_sn = QLabel(f'Serial Number: <b>{self._current_sn}</b>')
            lbl_sn.setStyleSheet('font-size: 12px;')

            lbl_msg = QLabel('Please register your Serial Number at:')
            lbl_msg.setStyleSheet('font-size: 12px;')

            lbl_link = QLabel('<a href="" style="color: #004ec5;"></a>')
            lbl_link.setOpenExternalLinks(True)
            lbl_link.setStyleSheet('font-size: 12px;')

            btn_ok = QPushButton('OK')
            btn_ok.setFixedWidth(80)
            btn_ok.clicked.connect(dlg.accept)

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_row.addWidget(btn_ok)

            dlg_layout.addWidget(lbl_title)
            dlg_layout.addWidget(lbl_sn)
            dlg_layout.addWidget(lbl_msg)
            dlg_layout.addWidget(lbl_link)
            dlg_layout.addSpacing(6)
            dlg_layout.addLayout(btn_row)
            dlg.exec_()
            self.status.setVisible(False)
            return

        self.timer.stop()
        self.activate.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setVisible(True)
        self.status.setText('Starting activation...')

        self._progress_val = 0
        self._progress_timer.start(600)

        self.worker = ActivationThread(device_info=self._device_info)
        self.worker.status.connect(self._on_activation_status)
        self.worker.waiting.connect(self._on_waiting)
        self.worker.success.connect(self.on_success)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_success(self, msg):
        self._progress_timer.stop()
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText('Activated Successfully!')
        dlg = SuccessDialog(self, device_info=self._device_info)
        dlg.exec_()
        self.progress.setVisible(False)
        self.status.setVisible(False)
        self.activate.setEnabled(True)
        self.timer.start(1000)

    def on_error(self, msg):
        self._progress_timer.stop()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        err = QMessageBox(self)
        err.setWindowTitle('Error')
        err.setText('Activation failed.')
        err.setInformativeText(msg)
        err.setIcon(QMessageBox.Critical)
        err.exec_()
        self.status.setText('Error occurred')
        self.status.setVisible(True)
        self.timer.start(1000)

# ========================== ENTRY POINT ==========================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
