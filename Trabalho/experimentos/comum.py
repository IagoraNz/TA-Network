"""Caminhos, lista de controladores e inicialização segura do controlador sob teste."""

import os
import subprocess
import time

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RES = os.path.join(BASE, 'resultados')
FIG = os.path.join(BASE, 'artigo', 'figuras')
PORTA = 6653

CONTROLADORES = [  # (rótulo, script relativo a BASE)
    ('base', 'Controlador-v2.py'),
    ('refat1_selectors', 'refatoracoes/Controlador-v3-selectors.py'),
    ('refat2_threads', 'refatoracoes/Controlador-v3-threads.py'),
    ('refat3_asyncio', 'refatoracoes/Controlador-v3-asyncio.py'),
]

# Rótulo, legenda, cor, marcador e estilo de linha: idênticos em todas as figuras
SERIES = [
    ('base', 'Base (síncrono)', '#e3242b', 'o', '-'),
    ('refat1_selectors', 'Refat. 1 (selectors)', '#1f4fe0', 's', '--'),
    ('refat2_threads', 'Refat. 2 (threads)', '#138a13', '^', '-.'),
    ('refat3_asyncio', 'Refat. 3 (asyncio)', '#c21fc2', 'd', ':'),
]

ESTILO_FIG = {
    'font.family': 'serif', 'font.serif': ['Times New Roman', 'Times', 'Nimbus Roman', 'DejaVu Serif'],
    'font.size': 11, 'axes.labelweight': 'bold', 'mathtext.fontset': 'stix',
}


def pasta(*partes):
    """Cria (se necessário) e devolve resultados/<partes...>."""
    p = os.path.join(RES, *partes)
    os.makedirs(p, exist_ok=True)
    return p


def porta_em_uso(porta=PORTA):
    """Há socket em LISTEN na porta? Lido de /proc para não abrir conexão com o controlador."""
    for arq in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            linhas = open(arq).read().split('\n')[1:]
        except FileNotFoundError:
            continue
        for l in linhas:
            c = l.split()
            if len(c) > 3 and c[3] == '0A' and int(c[1].rsplit(':', 1)[1], 16) == porta:
                return True
    return False


def iniciar_controlador(script, log_path, extra=('--quiet',), timeout=5.0):
    """
    Inicia o controlador e só retorna quando ELE estiver escutando a porta.
    Aborta se a porta já estiver ocupada: sem essa checagem, um processo antigo
    responde no lugar do controlador sob teste e os dados ficam inválidos.
    """
    if porta_em_uso():
        raise RuntimeError(f'porta {PORTA} já está em uso por outro processo; '
                           f'encerre-o antes do experimento (ss -ltnp | grep {PORTA})')
    log = open(log_path, 'w')
    proc = subprocess.Popen(['python3', '-u', os.path.join(BASE, script), *extra],
                            stdout=log, stderr=subprocess.STDOUT, cwd=BASE)
    limite = time.time() + timeout
    while time.time() < limite:
        if proc.poll() is not None:
            raise RuntimeError(f'{script} terminou ao iniciar (veja {log_path})')
        if porta_em_uso():
            return proc
        time.sleep(0.05)
    proc.kill()
    raise RuntimeError(f'{script} não abriu a porta {PORTA} em {timeout} s')


def parar_controlador(proc):
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    limite = time.time() + 5
    while porta_em_uso() and time.time() < limite:
        time.sleep(0.05)
