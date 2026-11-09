#!/usr/bin/python3
"""Cache the official engine using resumable HTTP byte ranges."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request
import zipfile

URL = os.environ.get('SIMULATOR_URL', 'https://sz-rm-rmua-dispatch-prod.oss-cn-shenzhen.aliyuncs.com/b39a0194e982f0d987153c6016feb325/simulator_12.0.0.5.zip')
CACHE = Path(os.environ.get('SIM_ASSET_CACHE', str(Path.home() / '.cache/rmua2026-assets')))
CACHE.mkdir(parents=True, exist_ok=True)
archive = CACHE / 'simulator_12.0.0.5.zip'
with urllib.request.urlopen(urllib.request.Request(URL, method='HEAD'), timeout=30) as response:
    size = int(response.headers['Content-Length'])
    etag = response.headers.get('ETag', '')
metadata = {'url': URL, 'size': size, 'etag': etag}
record = CACHE / 'engine.json'
if archive.exists() and archive.stat().st_size == size and record.exists() and json.loads(record.read_text()) == metadata:
    print(f'Using cached engine: {archive}', flush=True)
    raise SystemExit(0)
identity = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:16]
parts = CACHE / ('parts-' + identity)
parts.mkdir(exist_ok=True)
chunk_size = 8 * 1024 * 1024
count = (size + chunk_size - 1) // chunk_size

def download(index):
    start, end = index * chunk_size, min(size, (index + 1) * chunk_size) - 1
    path = parts / str(index)
    if path.exists() and path.stat().st_size == end - start + 1:
        return end - start + 1
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{end}'})
            with urllib.request.urlopen(req, timeout=45) as response:
                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                    raise RuntimeError('server returned an unexpected byte range')
                with path.with_suffix('.part').open('wb') as output:
                    shutil.copyfileobj(response, output, 256 * 1024)
            if path.with_suffix('.part').stat().st_size != end - start + 1:
                raise RuntimeError('incomplete byte range')
            path.with_suffix('.part').replace(path)
            return end - start + 1
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

print(f'Downloading official engine: {size / 1024**3:.2f} GiB, resumable ranges', flush=True)
completed = 0
workers = int(os.environ.get('SIM_DOWNLOAD_WORKERS', '32'))
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
    pending = {pool.submit(download, index) for index in range(count)}
    while pending:
        done, pending = concurrent.futures.wait(pending, timeout=10, return_when=concurrent.futures.FIRST_COMPLETED)
        completed += sum(future.result() for future in done)
        received = 0
        for part in parts.iterdir():
            try:
                received += part.stat().st_size
            except FileNotFoundError:
                pass
        received = min(size, received)
        print(f'Engine: {received / size:.1%} ({received / 1024**2:.0f}/{size / 1024**2:.0f} MiB)', flush=True)
temporary = archive.with_suffix('.zip.part')
with temporary.open('wb') as output:
    for index in range(count):
        with (parts / str(index)).open('rb') as source:
            shutil.copyfileobj(source, output, 1024 * 1024)
print('Checking ZIP integrity...', flush=True)
with zipfile.ZipFile(temporary) as engine_zip:
    bad_file = engine_zip.testzip()
    if bad_file:
        raise RuntimeError('ZIP checksum failed: ' + bad_file)
temporary.replace(archive)
record.write_text(json.dumps(metadata, indent=2) + '\n')
shutil.rmtree(parts)
print(f'Engine ready: {archive}', flush=True)
