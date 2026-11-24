"""MiniTube local server: serves index.html plus a tiny Piped-compatible API backed by yt-dlp.

Run on a PC in the same Wi-Fi as the iPhone:  python server.py
then open the printed http://<PC-IP>:8000 address in Safari on the iPhone.
"""
import json
import re
import socket
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from yt_dlp import YoutubeDL

ROOT = Path(__file__).parent
PORT = 8000
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
# shortcut: YouTube removed its trending page, so home borrows a public Piped list and falls back to a search.
TRENDING = 'https://api.piped.private.coffee/trending?region=VN'
FALLBACK_HOME = 'nhạc mới nhất'
OPTS = {'quiet': True, 'no_warnings': True, 'skip_download': True}


def item(e):
    vid = e['id']
    return {
        'type': 'stream', 'url': '/watch?v=' + vid, 'title': e.get('title'),
        'thumbnail': f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg',
        'uploaderName': e.get('channel') or e.get('uploader'), 'uploaderAvatar': None,
        'duration': -1 if e.get('live_status') == 'is_live' else e.get('duration') or 0,
        'views': e['view_count'] if e.get('view_count') is not None else -1, 'uploadedDate': None,
    }


def search(q):
    with YoutubeDL({**OPTS, 'extract_flat': True}) as y:
        r = y.extract_info('ytsearch20:' + q, download=False)
    return [item(e) for e in r.get('entries') or [] if VIDEO_ID.match(e.get('id') or '')]


def trending():
    try:
        with urllib.request.urlopen(TRENDING, timeout=15) as r:
            data = json.load(r)
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return search(FALLBACK_HOME)


def streams(vid):
    with YoutubeDL(OPTS) as y:
        d = y.extract_info('https://www.youtube.com/watch?v=' + vid, download=False)
    # YouTube's HLS master playlist has H.264 + AAC variants that iOS plays natively.
    # shortcut: its links are tied to this PC's public IP, so the iPhone must share the network;
    # proxy the playlist and segments here if it ever has to work from elsewhere.
    hls = next((f['manifest_url'] for f in d.get('formats') or []
                if f.get('manifest_url') and 'm3u8' in (f.get('protocol') or '')), None)
    ud = d.get('upload_date') or ''
    return {
        'title': d.get('title'), 'uploader': d.get('channel') or d.get('uploader'), 'uploaderAvatar': None,
        'thumbnailUrl': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',
        'uploaderSubscriberCount': d.get('channel_follower_count') or -1,
        'views': d['view_count'] if d.get('view_count') is not None else -1,
        'uploadDate': f'{ud[:4]}-{ud[4:6]}-{ud[6:]}' if len(ud) == 8 else '',
        'videoStreams': [], 'hls': hls, 'livestream': bool(d.get('is_live')), 'relatedStreams': [],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        m = re.fullmatch(r'/streams/([A-Za-z0-9_-]{11})', u.path)
        try:
            if u.path == '/trending':
                return self.send_json(trending())
            if u.path == '/search':
                q = urllib.parse.parse_qs(u.query).get('q', [''])[0].strip()
                return self.send_json({'items': search(q) if q else []})
            if m:
                return self.send_json(streams(m.group(1)))
        except Exception as e:  # yt-dlp errors (bot check, removed video) go back to the app as text
            return self.send_json({'error': str(e)}, 500)
        if u.path in ('/', '/index.html'):  # serve only the app, never other files in this folder
            return super().do_GET()
        self.send_error(404)

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(('8.8.8.8', 80))  # no packet is sent; this only picks the outgoing interface
        return s.getsockname()[0]


if __name__ == '__main__':
    print(f'MiniTube: mở trên iPhone (cùng Wi-Fi): http://{lan_ip()}:{PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
