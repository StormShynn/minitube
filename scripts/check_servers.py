"""Find public Piped / Invidious servers that can really play video in MiniTube, and write servers.json.

Run every hour by .github/workflows/servers.yml. MiniTube loads servers.json on every start and
tries the servers in this order, so the healthiest and fastest come first.
A server passes a test video when: its API answers with a CORS header (Safari needs it),
it offers a file MiniTube can play (muxed mp4 or HLS), and the first KB of that file downloads.
"""
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'servers.json'
TEST_VIDEOS = ['dQw4w9WgXcQ', 'jNQXAC9IVRw', 'kJQP7kiw5Fk']  # music video, oldest video, most-viewed video
ORIGIN = 'https://stormshynn.github.io'
HOST = re.compile(r'https://[a-z0-9.-]+\.[a-z]{2,}')
SOURCES = [
    ('piped', 'json', 'https://raw.githubusercontent.com/jayxdcode/piped-instances/main/public/minimal.json'),
    ('piped', 'md', 'https://raw.githubusercontent.com/TeamPiped/documentation/main/content/docs/public-instances/index.md'),
    ('invidious', 'md', 'https://raw.githubusercontent.com/iv-org/documentation/master/docs/instances.md'),
    ('invidious', 'json', 'https://api.invidious.io/instances.json?sort_by=health'),
]


def fetch(url, timeout=20, rng=None):
    headers = {'User-Agent': 'MiniTube-server-check', 'Origin': ORIGIN}
    if rng:
        headers['Range'] = rng
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(1024 if rng else None)


def urls_from(kind, fmt, body):
    text = body.decode('utf-8', 'replace')
    if fmt == 'md':  # Piped: "| name | https://api... |" table; Invidious: "* [name](https://host)" list
        pattern = r'\|\s*(https://[^\s|]+)\s*\|' if kind == 'piped' else r'^\* \[[^\]]+\]\((https://[^)\s]+)\)'
        return re.findall(pattern, text, re.M)
    data = json.loads(text)
    if kind == 'piped':
        return [i.get('api_url', '') for i in data.get('instances', [])]
    return [info.get('uri', '') for _, info in data if info.get('type') == 'https' and info.get('api')]


def candidates():
    found = {}
    if OUT.exists():  # keep testing servers that worked before, even if a list drops them
        for s in json.loads(OUT.read_text(encoding='utf-8')).get('servers', []):
            found[s['url']] = s['type']
    for kind, fmt, url in SOURCES:
        try:
            for u in urls_from(kind, fmt, fetch(url)[2]):
                u = u.strip().rstrip('/')
                if HOST.fullmatch(u):
                    found.setdefault(u, kind)
        except Exception as e:  # one dead list must not stop the others
            print(f'source failed: {url}: {e}', file=sys.stderr)
    return found


def playable(kind, base, data):
    """The file MiniTube would play for this API answer, as an absolute URL (same rule as index.html)."""
    if kind == 'piped':
        mux = [s for s in data.get('videoStreams', []) if not s.get('videoOnly') and 'mp4' in (s.get('mimeType') or '')]
        best = next((s for s in mux if s.get('itag') == 18), mux[0] if mux else None)
        src = best['url'] if best else data.get('hls')
    else:
        mux = [s for s in data.get('formatStreams', []) if (s.get('type') or '').startswith('video/mp4')]
        src = mux[-1]['url'] if mux else None
    return urllib.parse.urljoin(base + '/', src) if src else None


def check(url, kind):
    passed, start = 0, time.time()
    for vid in TEST_VIDEOS:
        api = f'{url}/streams/{vid}' if kind == 'piped' else f'{url}/api/v1/videos/{vid}?local=true'
        try:
            status, headers, body = fetch(api)
            if 'access-control-allow-origin' not in headers:
                return url, kind, 0, 0  # Safari would block every request: never usable
            src = playable(kind, url, json.loads(body))
            if src and fetch(src, rng='bytes=0-1023')[0] in (200, 206):
                passed += 1
        except Exception:
            pass
    return url, kind, passed, round(time.time() - start, 1)


def main():
    found = candidates()
    print(f'testing {len(found)} servers with {len(TEST_VIDEOS)} videos each')
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda item: check(*item), found.items()))
    for url, kind, passed, secs in sorted(results, key=lambda r: (-r[2], r[3])):
        print(f'{passed}/{len(TEST_VIDEOS)}  {secs:>5}s  {kind:9}  {url}')
    # Most videos passed first, then speed in 5 s steps (exact seconds would reorder, and commit, every hour).
    good = sorted((r for r in results if r[2] > 0), key=lambda r: (-r[2], int(r[3] // 5), r[0]))
    if not good:
        print('no working server: keeping the previous servers.json')
        return
    # Only stable fields, so the file (and the repo) changes only when the usable set or its order changes.
    servers = [{'type': kind, 'url': url} for url, kind, _, _ in good]
    OUT.write_text(json.dumps({'servers': servers}, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {len(servers)} servers to {OUT.name}')


if __name__ == '__main__':
    main()
