"""Read-only ErsatzTV XMLTV/M3U guide; all times are timezone-aware."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import xml.etree.ElementTree as ET

ROME = ZoneInfo('Europe/Rome')

def xmltime(value):
    value = value.strip()
    # XMLTV permits compact partial dates; incomplete programme times are skipped.
    if not re.fullmatch(r'\d{14}(?:\s+[+-]\d{4})?', value):
        raise ValueError('Incomplete XMLTV timestamp')
    if ' ' not in value:
        return datetime.strptime(value, '%Y%m%d%H%M%S').replace(tzinfo=ROME)
    return datetime.strptime(value, '%Y%m%d%H%M%S %z').astimezone(ROME)

def parse_guide(xml, m3u=''):
    root = ET.fromstring(xml)
    channels = {}
    for el in root.findall('channel'):
        cid = el.get('id', '')
        names = [n.text.strip() for n in el.findall('display-name') if n.text]
        if cid:
            channels[cid] = {'id': cid, 'name': names[0] if names else cid, 'programmes': []}
    for line in m3u.splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        match = re.search(r'tvg-id="([^"]+)"', line)
        if match:
            cid = match.group(1)
            channels.setdefault(cid, {'id': cid, 'name': line.rsplit(',', 1)[-1].strip(), 'programmes': []})
    for el in root.findall('programme'):
        cid = el.get('channel')
        if cid not in channels:
            continue
        try:
            start, end = xmltime(el.get('start', '')), xmltime(el.get('stop', ''))
        except ValueError:
            continue
        if end <= start:
            continue
        channels[cid]['programmes'].append({
            'start': start, 'end': end,
            'title': el.findtext('title', 'Titolo non disponibile'),
            'description': el.findtext('desc', ''),
            'year': el.findtext('date', ''),
            'categories': [e.text for e in el.findall('category') if e.text],
        })
    for ch in channels.values():
        ch['programmes'].sort(key=lambda p: p['start'])
    def sortkey(ch):
        n = re.match(r'\d+', ch['name'])
        return (int(n.group()) if n else 9999, ch['name'].casefold())
    return sorted(channels.values(), key=sortkey)

def now_next(ch, now):
    current = next((p for p in ch['programmes'] if p['start'] <= now < p['end']), None)
    following = next((p for p in ch['programmes'] if p['start'] > now), None)
    return current, following

def on_date(ch, date):
    return [p for p in ch['programmes'] if p['start'].astimezone(ROME).date() == date]
