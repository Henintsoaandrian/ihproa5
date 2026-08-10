import sys
import os
import json
import ssl
import certifi
import urllib.request
import urllib.parse
import threading
import platform

# Patch pour construct_typed (inclus dans l'original)
try:
    import construct_typing
    sys.modules['construct_typed'] = construct_typing
except ImportError:
    try:
        import construct_typed
    except ImportError:
        print("Erreur: ni construct_typing ni construct_typed n'est installé.")
        sys.exit(1)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox, QDialog
)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QFont, QPainterPath

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.diagnostics import DiagnosticsService

# ========================== CONSTANTS ==========================
BACKEND_URL        = 'http://api.mobidocserver.com/iHPro_Tool_A5/A5/server.php'
VALIDATE_URL       = 'https://api.mobidocserver.com/iHPro_Tool_A5/A5/validate.php'
TELEGRAM_URL       = 'https://api.mobidocserver.com/iHPro_Tool_A5/A5/telegramreport.php'
TELEGRAM_BOT_TOKEN = '8878915882:AAHcLQFjNsEmhO8gOQ6cT4ioC9S9iualdVs'
TELEGRAM_CHAT_ID   = '1913084477'

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

def check_sn_registered(sn):
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        url = f'{VALIDATE_URL}?sn={sn}'
        req = urllib.request.urlopen(url, timeout=10, context=ctx)
        data = json.loads(req.read().decode())
        return data.get('valid', False)
    except Exception:
        return False

# ========================== CLICKABLE LABEL ==========================
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ========================== SUCCESS DIALOG (simulé) ==========================
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

# ========================== MAIN WINDOW ==========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Dhmf Software Bypass A5-A6 Tool V1.0')
        self.setFixedSize(500, 330)
        self.setContentsMargins(0, 0, 0, 0)

        # ---- Image de fond ----
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, 500, 330)
        self.bg_label.setScaledContents(True)
        bg_path = resource_path('fond.png')
        if os.path.exists(bg_path):
            self.bg_label.setPixmap(QPixmap(bg_path))
        else:
            self.bg_label.setStyleSheet("background: #e8f0fe;")
        self.bg_label.lower()

        # ---- Logo comme icône ----
        logo_path = resource_path('logo.png')
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # ---- Variables d'état ----
        self._device_info    = {}
        self._current_sn     = ''
        self._reported_udids = set()

        # ---- Widgets ----
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

        # --- Bouton Activate ---
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

        # ---- Layout ----
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self.lbl_uuid)
        layout.addWidget(self.lbl_device)
        layout.addWidget(self.lbl_udid)
        layout.addWidget(self.lbl_imei)
        layout.addWidget(self.lbl_sn)
        layout.addSpacing(8)
        layout.addWidget(self.status)
        layout.addWidget(self.activate)

        central = QWidget(self)
        central.setLayout(layout)
        central.setGeometry(0, 0, 500, 330)
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        central.setAttribute(Qt.WA_TranslucentBackground)

        # ---- Style global ----
        self.setStyleSheet("""
            QMainWindow { background: transparent; }
            QLabel { background-color: rgba(255,255,255,0.75); border-radius: 4px; padding: 2px 4px; }
            QLabel#statusLabel { color: #004ec5; font-weight: bold; background-color: rgba(255,255,255,0.85); }
        """)

        # ---- Connexions ----
        self.activate.clicked.connect(self.start_activation)

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

            try:
                chip_id = lockdown.get_value(key='UniqueChipID')
                if isinstance(chip_id, int):
                    ecid = hex(chip_id).upper().replace('0X', '')
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

    # ---------- Start activation (simulée) ----------
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

            lbl_link = QLabel('<a href="https://frpkingdigitalstore.com" style="color: #004ec5;">frpkingdigitalstore.com</a>')
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

        # Si le SN est enregistré, on simule une activation réussie
        report_async(self._device_info, 'Activated ✅ (simulated)')
        self.status.setText('Activation succeeded (simulated)')
        dlg_success = SuccessDialog(self, device_info=self._device_info)
        dlg_success.exec_()
        self.status.setVisible(False)

# ========================== ENTRY POINT ==========================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())