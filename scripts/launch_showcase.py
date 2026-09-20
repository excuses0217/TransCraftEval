"""Start or reuse only our isolated workspace; never kill an occupied port."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    port = int(os.getenv('FACE_WATCH_PORT', '8770'))
    base = f'http://127.0.0.1:{port}'
    url = base+'/?workspace=validation#/overview'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def healthy():
        try:
            with opener.open(base+'/api/settings', timeout=1) as response:
                return json.load(response).get('profile') == 'showcase'
        except Exception:
            return False
    def show():
        print(f'映鉴已启动：{url}', flush=True)
        if os.getenv('FACE_WATCH_NO_BROWSER') != '1':
            webbrowser.open(url)
    if healthy():
        show()
        return
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            raise SystemExit(f'端口 {port} 已被其他服务占用。请设置 FACE_WATCH_PORT，不会停止原服务。')
    child = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'face_watch.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=root,
        env={**os.environ, 'FACE_WATCH_PROFILE': 'showcase'},
    )
    try:
        for _ in range(120):
            if child.poll() is not None:
                raise SystemExit('服务启动失败，请查看错误信息。')
            if healthy():
                show()
                print('关闭此终端或按 Ctrl+C 停止；审核记录下次启动会保留。', flush=True)
                raise SystemExit(child.wait())
            time.sleep(.25)
        raise SystemExit('启动超时。')
    except KeyboardInterrupt:
        pass
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
