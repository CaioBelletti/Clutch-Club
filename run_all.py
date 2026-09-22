import os, subprocess, sys, time, webbrowser, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent

print(f"[BOOT DEBUG] run_all = {Path(__file__).resolve()}")
print(f"[BOOT DEBUG] ROOT = {ROOT}")

bot_main = ROOT / "clutch_bot" / "main.py"

print(f"[BOOT DEBUG] clutch_bot/main.py = {bot_main.resolve()}")
print(f"[BOOT DEBUG] main.py existe = {bot_main.exists()}")

if bot_main.exists():
    conteudo = bot_main.read_text(encoding="utf-8", errors="replace")
    print(f"[BOOT DEBUG] main.py bytes = {len(conteudo)}")
    print(f"[BOOT DEBUG] contém V3.8.4.2 = {'V3.8.4.2' in conteudo}")
    print(f"[BOOT DEBUG] contém erro 403 antigo = {'[BUYLIST MODE] falha:' in conteudo}")

PORT=os.getenv('PORT','8000')

def port_in_use(host='127.0.0.1', port=8000):
    import socket
    try:
        with socket.create_connection((host,int(port)),timeout=.35): return True
    except OSError: return False

if port_in_use(port=PORT):
    print(f'[LOCK] BLOQUEADO: a porta {PORT} já está em uso.')
    print('[LOCK] Provavelmente outra versão do Clutch OS ainda está aberta. Feche-a e tente novamente.')
    raise SystemExit(3)

db_url=(os.getenv('DATABASE_URL') or '').strip().lower()
if db_url.startswith(('postgres://','postgresql://','postgresql+psycopg://')):
    print('[DATA] Railway/PostgreSQL detectado: recovery SQLite local ignorado.')
else:
    from data_bootstrap import prepare
    prepare()
HOST='127.0.0.1'
URL=f'http://{HOST}:{PORT}/'
BOOT_URL=f'http://{HOST}:{PORT}/identity-bootstrap-v351'
procs=[]

def wait_web(timeout=15):
    end=time.time()+timeout
    while time.time()<end:
        try:
            with urllib.request.urlopen(f'{URL}health',timeout=1) as r:
                if r.status==200:return True
        except Exception:
            time.sleep(.35)
    return False

try:
    print('[CLUTCH] Iniciando API + Control Center...')
    api=subprocess.Popen([sys.executable,'-m','uvicorn','clutch_os.api.app:app','--host','0.0.0.0','--port',PORT],cwd=ROOT)
    procs.append(api)
    if wait_web():
        print(f'[CLUTCH WEB] Control Center iniciado: {URL}')
        if not os.getenv('RAILWAY_ENVIRONMENT'):
            try:webbrowser.open(BOOT_URL)
            except Exception:pass
    else:
        print('[CLUTCH WEB] AVISO: o Control Center nao respondeu dentro de 15 segundos.')
    print('[CLUTCH] Iniciando Discord Bot...')
    bot=subprocess.Popen([sys.executable,'-m','clutch_bot.main'],cwd=ROOT)
    procs.append(bot)
    raise SystemExit(bot.wait())
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
