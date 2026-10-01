#!/usr/bin/env python3
"""
Refatoração 2 - Uma thread por switch (threading) com sockets bloqueantes.

Mudanças em relação ao Controlador-v2.py:
  - A thread principal apenas executa accept() (bloqueante, sem busy-wait) e
    entrega cada conexão a uma thread dedicada: os handshakes ocorrem em paralelo.
  - Cada thread usa recv() bloqueante com buffer + enquadramento: enquanto um
    switch está ocioso, a thread dorme no kernel e libera o GIL.
  - Limitação: o GIL impede paralelismo real de CPU entre threads Python; o
    ganho vem da eliminação do busy-wait e da independência entre switches.
"""

import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from of10 import HELLO, FEATURES, OFPT_FEATURES_REPLY, responder, extrair_mensagens

HOST, PORT = '0.0.0.0', int(os.environ.get('OF_PORT', 6653))


def atender_switch(conn, addr):
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    buf, dpid = bytearray(), None
    try:
        conn.sendall(HELLO)
        while True:
            dados = conn.recv(65536)
            if not dados:
                break
            buf += dados
            saida = bytearray()
            for msg_type, xid, body in extrair_mensagens(buf):
                if msg_type == OFPT_FEATURES_REPLY:
                    dpid = FEATURES.unpack_from(body)[0]
                    print(f'[{time.strftime("%H:%M:%S")}] [OK] Handshake com DPID {dpid} '
                          f'({threading.current_thread().name})', flush=True)
                resp = responder(msg_type, xid, body)
                if resp:
                    saida += resp
            if saida:
                conn.sendall(saida)
    except OSError:
        pass
    finally:
        print(f'[-] Switch {dpid} desconectado', flush=True)
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(128)
    print(f'=== Controlador v3 (threading) em {HOST}:{PORT} ===', flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=atender_switch, args=(conn, addr), daemon=True).start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
