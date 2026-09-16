#!/usr/bin/env python3
"""PAL-friendly read-only TV guide launched by 240-MP's display handoff."""
import os
import sys
import json
import textwrap
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from PyQt5 import QtCore, QtGui, QtWidgets
from guide_data import ROME, parse_guide, now_next, on_date

BASE = 'http://PMS-LOCAL-IP:8409'
CACHE = Path.home() / '.cache' / '240mp-televideo'
WHITE, CYAN, YELLOW, GREEN, RED = '#eeeeee', '#00ffff', '#ffff00', '#40ff60', '#ff6060'


class RemoteInput(QtCore.QObject):
    """Read lircd-uinput directly while 240-MP has handed the display over."""
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.device = None
        self.notifier = None
        try:
            from evdev import InputDevice, ecodes, list_devices
            self.ecodes = ecodes
            for path in list_devices():
                candidate = InputDevice(path)
                if candidate.name == 'lircd-uinput':
                    self.device = candidate
                    break
                candidate.close()
            if not self.device:
                return
            self.device.grab()
            self.callback = callback
            self.notifier = QtCore.QSocketNotifier(
                self.device.fd, QtCore.QSocketNotifier.Read, self)
            self.notifier.activated.connect(self.read_events)
        except Exception:
            self.close()

    def read_events(self):
        try:
            for event in self.device.read():
                if event.type != self.ecodes.EV_KEY or event.value != 1:
                    continue
                action = {
                    self.ecodes.KEY_UP: 'up', self.ecodes.KEY_DOWN: 'down',
                    self.ecodes.KEY_LEFT: 'left', self.ecodes.KEY_RIGHT: 'right',
                    self.ecodes.KEY_OK: 'ok', self.ecodes.KEY_ENTER: 'ok',
                    self.ecodes.KEY_SELECT: 'ok', self.ecodes.KEY_BACK: 'back',
                    self.ecodes.KEY_ESC: 'back', self.ecodes.KEY_EXIT: 'back',
                }.get(event.code)
                if action:
                    self.callback(action)
        except BlockingIOError:
            pass
        except Exception:
            self.close()

    def close(self):
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.device:
            try:
                self.device.ungrab()
            except Exception:
                pass
            self.device.close()
            self.device = None

class Fetch(QtCore.QThread):
    done = QtCore.pyqtSignal(object, str)
    def run(self):
        try:
            def get(path):
                with urlopen(Request(BASE + path, headers={'User-Agent':'240MP-Televideo/1.0'}), timeout=12) as r:
                    data = r.read(20 * 1024 * 1024 + 1)
                if len(data) > 20 * 1024 * 1024:
                    raise ValueError('Guida troppo grande')
                return data.decode('utf-8-sig')
            xml = get('/iptv/xmltv.xml')
            m3u = get('/iptv/channels.m3u')
            channels = parse_guide(xml, m3u)
            CACHE.mkdir(parents=True, exist_ok=True)
            data = json.dumps({'xml':xml, 'm3u':m3u, 'time':datetime.now(ROME).isoformat()})
            tmp = CACHE / 'guide.tmp'
            tmp.write_text(data, encoding='utf-8')
            tmp.replace(CACHE / 'guide.json')
            self.done.emit(channels, 'AGGIORNATO ' + datetime.now(ROME).strftime('%H:%M'))
        except Exception:
            # Do not display raw network exceptions or URLs with possible credentials.
            self.done.emit(None, 'SERVER NON RAGGIUNGIBILE - GUIDA IN CACHE')

class Guide(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Televideo')
        self.channels = []
        self.page = 100
        self.index = 0
        self.programme = 0
        self.detail_scroll = 0
        self.day = datetime.now(ROME).date()
        self.message = 'CARICAMENTO GUIDA...'
        self.fetcher = None
        self.remote = RemoteInput(self.action, self)
        self.joysticks = []
        self.pg = None
        try:
            data = json.loads((CACHE / 'guide.json').read_text(encoding='utf-8'))
            self.channels = parse_guide(data['xml'], data.get('m3u',''))
            stamp = datetime.fromisoformat(data['time']).astimezone(ROME)
            self.message = 'CACHE DEL ' + stamp.strftime('%d/%m %H:%M')
        except Exception:
            pass
        try:
            os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
            os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
            import pygame
            self.pg = pygame
            pygame.joystick.init()
            self.joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
            for stick in self.joysticks:
                stick.init()
            # The event queue needs the SDL video subsystem, but never creates a window.
            pygame.display.init()
        except Exception:
            self.pg = None
        self.controls = QtCore.QTimer(self)
        self.controls.timeout.connect(self.poll_pad)
        self.controls.start(35)
        self.clock = QtCore.QTimer(self)
        self.clock.timeout.connect(self.update)
        self.clock.start(1000)
        self.auto = QtCore.QTimer(self)
        self.auto.timeout.connect(self.refresh)
        self.auto.start(5 * 60 * 1000)
        self.refresh()

    def refresh(self):
        if self.fetcher and self.fetcher.isRunning():
            return
        self.fetcher = Fetch(self)
        self.fetcher.done.connect(self.loaded)
        self.fetcher.start()

    def loaded(self, channels, message):
        if channels is not None:
            old_id = self.channels[self.index]['id'] if self.channels else None
            self.channels = channels
            self.index = next((i for i,c in enumerate(channels) if c['id']==old_id),0)
        self.message = message
        self.programme = min(self.programme, max(0, len(self.entries())-1))
        self.update()

    def entries(self):
        return on_date(self.channels[self.index], self.day) if self.channels else []

    def poll_pad(self):
        if not self.pg:
            return
        try:
            for event in self.pg.event.get():
                if event.type == self.pg.JOYBUTTONDOWN:
                    action = {0:'ok',1:'back',2:'refresh',6:'back'}.get(event.button)
                    if action:self.action(action)
                elif event.type == self.pg.JOYHATMOTION:
                    x,y=event.value
                    if x:self.action('right' if x>0 else 'left')
                    if y:self.action('up' if y>0 else 'down')
                elif event.type == self.pg.JOYDEVICEADDED:
                    stick=self.pg.joystick.Joystick(event.device_index);stick.init();self.joysticks.append(stick)
        except Exception:
            self.pg = None

    def keyPressEvent(self, event):
        key=event.key()
        action={QtCore.Qt.Key_Return:'ok',QtCore.Qt.Key_Enter:'ok',QtCore.Qt.Key_Escape:'back',
                QtCore.Qt.Key_Backspace:'back',QtCore.Qt.Key_Up:'up',QtCore.Qt.Key_Down:'down',
                QtCore.Qt.Key_Left:'left',QtCore.Qt.Key_Right:'right',QtCore.Qt.Key_R:'refresh'}.get(key)
        if action:self.action(action)

    def action(self, action):
        if action=='refresh':self.refresh();return
        if action=='back':
            if self.page==100:self.close();return
            self.page=100 if self.page==200 else 200
        elif action=='ok' and self.channels:
            if self.page==100:self.page=200;self.programme=0
            elif self.page==200 and self.entries():self.page=300;self.detail_scroll=0
        elif action in ('up','down'):
            delta=1 if action=='down' else -1
            if self.page==100 and self.channels:self.index=(self.index+delta)%len(self.channels)
            elif self.page==200 and self.entries():self.programme=(self.programme+delta)%len(self.entries())
            elif self.page==300:self.detail_scroll=max(0,min(self.detail_scroll+delta, max(0,len(self.detail_lines())-10)))
        elif action in ('left','right'):
            delta=1 if action=='right' else -1
            if self.page==200:
                self.day+=timedelta(days=delta);self.programme=0
            elif self.page==100 and self.channels:self.index=(self.index+delta)%len(self.channels)
        self.update()

    def detail_lines(self):
        entries=self.entries()
        if not entries:return []
        p=entries[min(self.programme,len(entries)-1)]
        details=[]
        year=p['year']
        if year and year!='0':details.append('ANNO '+year[:4])
        if p['categories']:details+=textwrap.wrap(' / '.join(p['categories']),40)
        details+=['']+textwrap.wrap(p['description'] or 'Descrizione non presente nella guida.',40)
        return details

    def paintEvent(self, event):
        p=QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing,False)
        p.scale(self.width()/720.0,self.height()/576.0)
        p.fillRect(0,0,720,576,QtGui.QColor('black'))
        font=QtGui.QFont('DejaVu Sans Mono');font.setPixelSize(23);font.setBold(True);p.setFont(font)
        def line(row,text,color=WHITE,bg=None):
            if bg:p.fillRect(40,29+row*22,640,22,QtGui.QColor(bg))
            p.setPen(QtGui.QColor(color))
            # Fixed 40-column grid, sized for composite overscan.
            for i,char in enumerate(str(text)[:40]):p.drawText(42+i*16,47+row*22,char)
        now=datetime.now(ROME)
        line(0,f'{self.page:03}  TELEVIDEO       {now:%d/%m %H:%M}',WHITE,'#0000aa')
        line(2,'LA TUA TV - GUIDA PROGRAMMI',YELLOW)
        if self.page==100:
            line(3,'ORA E DOPO',CYAN)
            if not self.channels:line(6,'NESSUN CANALE DISPONIBILE',YELLOW)
            start=(self.index//4)*4
            for n,ch in enumerate(self.channels[start:start+4]):
                row=5+n*4;selected=start+n==self.index
                line(row,('> ' if selected else '  ')+ch['name'].upper(),YELLOW if selected else CYAN)
                current,nxt=now_next(ch,now)
                line(row+1,'ORA '+(current['title'] if current else 'Nessun titolo in guida'))
                line(row+2,(nxt['start'].strftime('%d/%m %H:%M')+' '+nxt['title']) if nxt else 'DOPO Nessun titolo in guida',GREEN)
            if self.channels:line(21,f'CANALE {self.index+1}/{len(self.channels)}',CYAN)
        elif self.channels:
            ch=self.channels[self.index]
            line(3,ch['name'].upper(),CYAN)
            line(4,self.day.strftime('%d/%m/%Y')+'   < GIORNO >',YELLOW)
            entries=self.entries()
            if self.page==200:
                if not entries:
                    line(8,'NESSUN PROGRAMMA IN GUIDA',YELLOW)
                    line(10,'PROVA UN ALTRO GIORNO CON < >')
                start=(self.programme//7)*7
                for n,entry in enumerate(entries[start:start+7]):
                    row=6+n*2;selected=start+n==self.programme
                    title=entry['start'].strftime('%H:%M')+' '+entry['title']
                    parts=textwrap.wrap(title,38) or ['']
                    line(row,('> ' if selected else '  ')+parts[0],YELLOW if selected else WHITE)
                    if len(parts)>1:line(row+1,'  '+parts[1],YELLOW if selected else WHITE)
                if entries:line(21,f'PROGRAMMA {self.programme+1}/{len(entries)}',CYAN)
            elif entries:
                entry=entries[min(self.programme,len(entries)-1)]
                for n,text in enumerate(textwrap.wrap(entry['title'].upper(),40)[:3]):line(6+n,text,YELLOW)
                line(9,f"{entry['start']:%H:%M} - {entry['end']:%H:%M}",CYAN)
                # Description uses ten rows; scroll handles longer synopsis.
                for n,text in enumerate(self.detail_lines()[self.detail_scroll:self.detail_scroll+10]):line(11+n,text)
        line(22,self.message[:40],GREEN if self.message.startswith('AGGIORNATO') else YELLOW)
        line(23,'A:APRI  B:INDIETRO  X:AGGIORNA',WHITE,'#0000aa')
        p.end()

    def closeEvent(self,event):
        # Keep the event loop alive until the bounded request finishes.
        if self.fetcher and self.fetcher.isRunning():
            self.message='CHIUSURA...';self.update()
            self.fetcher.finished.connect(self.close)
            event.ignore();return
        if self.pg:self.pg.quit()
        self.remote.close()
        event.accept()

if __name__=='__main__':
    app=QtWidgets.QApplication(sys.argv)
    widget=Guide()
    if '--preview' in sys.argv:
        widget.resize(720,576);widget.show()
        def save():
            widget.grab().save(sys.argv[sys.argv.index('--preview')+1]);widget.close()
        widget.fetcher.finished.connect(save)
    else:widget.showFullScreen()
    sys.exit(app.exec_())
