#!/usr/bin/env python3
"""240-MP Wi-Fi selector. No network changes until explicit Connetti."""
import os
import sys
import tempfile
import uuid
from PyQt5 import QtCore, QtWidgets


def fields(line):
    result, part, escaped = [], '', False
    for char in line:
        if escaped:
            part += char
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            result.append(part)
            part = ''
        else:
            part += char
    if escaped:
        part += '\\'
    return result + [part]


class Wifi(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Wi-Fi')
        self.secret_path = None
        self.networks = []
        self.busy = False
        self.job = None
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(35, 20, 35, 20)
        self.layout.setSpacing(3)
        self.title = QtWidgets.QLabel('Wi-Fi · A conferma · B indietro')
        self.layout.addWidget(self.title)
        self.status = QtWidgets.QLabel('Scegli una rete. Ethernet resta collegata.')
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)
        self.list = QtWidgets.QListWidget()
        self.list.itemActivated.connect(self.choose)
        self.layout.addWidget(self.list, 1)
        self.entry = QtWidgets.QLineEdit()
        self.entry.setEchoMode(QtWidgets.QLineEdit.Password)
        self.entry.setPlaceholderText('Password Wi-Fi')
        self.entry.hide()
        self.layout.addWidget(self.entry)
        self.keys = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(self.keys)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(2)
        self.upper = False
        self.buttons = []
        self.layout.addWidget(self.keys)
        self.keys.hide()
        self.build_keys()
        self.setStyleSheet('QWidget { background:#10202b; color:white; font-size:12px; } QPushButton { background:#234353; padding:2px; } QPushButton:focus,QListWidget::item:selected { background:#ca6a24; } QLineEdit { background:#263c49; }')
        self.installEventFilter(self)
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.joysticks = []
        try:
            os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
            import pygame
            self.pygame = pygame
            pygame.display.init()
            pygame.joystick.init()
            for index in range(pygame.joystick.get_count()):
                stick = pygame.joystick.Joystick(index)
                stick.init()
                self.joysticks.append(stick)
            self.last_axis = {}
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.poll)
            self.timer.start(40)
        except Exception:
            self.title.setText('Wi-Fi · Frecce/Invio · Esc indietro')
        self.scan()

    def run(self, args, done):
        if self.busy:
            return
        self.busy = True
        self.list.setEnabled(False)
        self.keys.setEnabled(False)
        job = QtCore.QProcess(self)
        self.job = job
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert('LC_ALL', 'C')
        job.setProcessEnvironment(env)
        def finish(code, *_):
            if self.job is not job:
                return
            output = bytes(job.readAllStandardOutput()).decode('utf-8', 'replace')
            self.job = None
            self.busy = False
            self.list.setEnabled(True)
            self.keys.setEnabled(True)
            job.deleteLater()
            done(code, output)
        job.finished.connect(finish)
        job.errorOccurred.connect(lambda error: finish(127) if error == QtCore.QProcess.FailedToStart else None)
        job.start('/usr/bin/nmcli', args)

    def scan(self):
        self.status.setText('Ricerca reti Wi-Fi…')
        self.run(['radio', 'wifi'], self.radio_checked)

    def radio_checked(self, code, output):
        if code or output.strip() != 'enabled':
            self.networks = []
            self.list.clear()
            self.list.addItems(['Attiva Wi-Fi e cerca', '← Torna a 240-MP'])
            self.list.setCurrentRow(0)
            self.list.setFocus()
            self.radio_off = True
            self.status.setText('Wi-Fi disattivato. A per attivarlo.')
            return
        self.radio_off = False
        self.run(['--wait', '15', '-t', '-e', 'yes', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', 'ifname', 'wlan0', '--rescan', 'yes'], self.scanned)

    def scanned(self, code, output):
        self.networks = []
        seen = set()
        for line in output.splitlines():
            row = fields(line)
            if len(row) != 3 or not row[0] or row[0] in seen:
                continue
            seen.add(row[0])
            self.networks.append(row)
        self.list.clear()
        for ssid, strength, security in self.networks:
            self.list.addItem(f'{ssid}  {strength}%  {security}')
        self.list.addItems(['↻ Cerca ancora', '← Torna a 240-MP'])
        self.list.setCurrentRow(0)
        self.list.setFocus()
        self.status.setText('Seleziona una rete.' if not code else 'Ricerca non riuscita: verificare Wi-Fi e permessi.')

    def choose(self):
        index = self.list.currentRow()
        if index == len(self.networks):
            if getattr(self, 'radio_off', False):
                self.run(['radio', 'wifi', 'on'], self.radio_enabled)
            else:
                self.scan()
            return
        if index == len(self.networks) + 1:
            self.close()
            return
        if index < 0:
            return
        self.selected = self.networks[index]
        if '802.1X' in self.selected[2] or 'EAP' in self.selected[2]:
            self.status.setText('Rete aziendale: configurazione avanzata necessaria.')
            return
        self.status.setText('Rete: ' + self.selected[0])
        self.list.hide()
        self.entry.clear()
        self.entry.show()
        self.entry.setEnabled(self.selected[2] not in ('', '--'))
        self.keys.show()
        self.buttons[0].setFocus()

    def radio_enabled(self, code, output):
        if code:
            self.status.setText('Impossibile attivare Wi-Fi: controllare blocco radio e permessi.')
        else:
            self.scan()

    def build_keys(self):
        for button in self.buttons:
            self.grid.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        chars = 'abcdefghijklmnopqrstuvwxyz' if not self.upper else 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        labels = list(chars + '0123456789!@#$%&*()-_=+[]{};:,./?\\|<>`~\'"') + ['Spazio', 'Maiusc', 'Cancella', 'Connetti', 'Indietro']
        for index, label in enumerate(labels):
            button = QtWidgets.QPushButton(label)
            button.setFocusPolicy(QtCore.Qt.StrongFocus)
            button.clicked.connect(lambda _, value=label: self.key(value))
            self.grid.addWidget(button, index // 10, index % 10)
            self.buttons.append(button)

    def key(self, value):
        if value == 'Maiusc':
            self.upper = not self.upper
            self.build_keys()
            self.buttons[0].setFocus()
        elif value == 'Cancella':
            self.entry.backspace()
        elif value == 'Indietro':
            self.back()
        elif value == 'Connetti':
            password = self.entry.text()
            secured = self.selected[2] not in ('', '--')
            if secured and not password:
                self.status.setText('Inserisci la password della rete.')
                return
            self.status.setText('Connessione in corso…')
            if secured and 'WEP' in self.selected[2]:
                self.status.setText('Rete WEP obsoleta: configurazione avanzata necessaria.')
                return
            if '\n' in password or '\r' in password:
                self.status.setText('La password non può contenere ritorni a capo.')
                return
            self.profile_uuid = str(uuid.uuid4())
            args = ['connection', 'add', 'type', 'wifi', 'ifname', 'wlan0',
                    'con-name', '240MP ' + self.selected[0], 'ssid', self.selected[0],
                    'connection.uuid', self.profile_uuid,
                    'connection.permissions', 'user:' + os.environ.get('USER', 'user'),
                    'connection.autoconnect', 'no']
            if secured:
                security = self.selected[2]
                method = 'sae' if 'WPA3' in security and 'WPA2' not in security else 'wpa-psk'
                args += ['wifi-sec.key-mgmt', method]
                # nmcli's supported passwd-file avoids shell arguments and TTY prompts.
                fd, self.secret_path = tempfile.mkstemp(prefix='240mp-wifi-', dir='/dev/shm')
                with os.fdopen(fd, 'w', encoding='utf-8') as secret:
                    secret.write('802-11-wireless-security.psk:' + password + '\n')
            self.run(args, self.profile_created)
            self.entry.clear()
        else:
            self.entry.insert(' ' if value == 'Spazio' else value)

    def profile_created(self, code, output):
        if code:
            self.connected(code, '')
            return
        args = ['--wait', '35', 'connection', 'up', 'uuid', self.profile_uuid, 'ifname', 'wlan0']
        if self.secret_path:
            args += ['passwd-file', self.secret_path]
        self.run(args, self.activated)

    def activated(self, code, output):
        self.clear_secret()
        if code:
            # Only remove the profile created by this attempt; no existing profile is edited.
            self.run(['connection', 'delete', 'uuid', self.profile_uuid], lambda *_: self.connected(code, ''))
        else:
            self.run(['connection', 'modify', 'uuid', self.profile_uuid,
                      'connection.autoconnect', 'yes'], self.connected)

    def clear_secret(self):
        if self.secret_path:
            try:
                os.unlink(self.secret_path)
            except FileNotFoundError:
                pass
            self.secret_path = None

    def connected(self, code, output):
        self.clear_secret()
        self.status.setText('Wi-Fi connesso. B per tornare a 240-MP.' if code == 0 else 'Connessione non riuscita. Controlla password e permessi, poi riprova.')
        self.buttons[-1].setFocus()

    def back(self):
        if self.busy:
            return
        if self.keys.isVisible():
            self.keys.hide()
            self.entry.clear()
            self.entry.hide()
            self.list.show()
            self.list.setFocus()
        else:
            self.close()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            if self.busy:
                return True
            if key == QtCore.Qt.Key_Escape:
                self.back()
                return True
            focused = QtWidgets.QApplication.focusWidget()
            if focused in self.buttons and key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                focused.click()
                return True
            if focused in self.buttons and key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right, QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
                shift = {QtCore.Qt.Key_Left:-1, QtCore.Qt.Key_Right:1, QtCore.Qt.Key_Up:-10, QtCore.Qt.Key_Down:10}[key]
                self.buttons[(self.buttons.index(focused) + shift) % len(self.buttons)].setFocus()
                return True
        return super().eventFilter(obj, event)

    def send_key(self, key):
        target = QtWidgets.QApplication.focusWidget() or self
        from PyQt5.QtGui import QKeyEvent
        for event in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            QtWidgets.QApplication.sendEvent(target, QKeyEvent(event, key, QtCore.Qt.NoModifier))

    def poll(self):
        p = self.pygame
        for event in p.event.get():
            key = None
            if event.type == p.JOYBUTTONDOWN:
                key = {0:QtCore.Qt.Key_Return, 1:QtCore.Qt.Key_Escape}.get(event.button)
            elif event.type == p.JOYHATMOTION:
                x, y = event.value
                key = (QtCore.Qt.Key_Right if x > 0 else QtCore.Qt.Key_Left) if x else ((QtCore.Qt.Key_Up if y > 0 else QtCore.Qt.Key_Down) if y else None)
            elif event.type == p.JOYAXISMOTION and event.axis in (0, 1):
                value = 1 if event.value > .6 else -1 if event.value < -.6 else 0
                old = self.last_axis.get(event.axis, 0)
                self.last_axis[event.axis] = value
                if value and value != old:
                    key = ((QtCore.Qt.Key_Right if value > 0 else QtCore.Qt.Key_Left) if event.axis == 0 else (QtCore.Qt.Key_Down if value > 0 else QtCore.Qt.Key_Up))
            if key is not None:
                self.send_key(key)

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            self.clear_secret()
            event.accept()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = Wifi()
    window.showFullScreen()
    sys.exit(app.exec_())
