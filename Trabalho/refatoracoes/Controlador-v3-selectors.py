#!/usr/bin/env python3
"""
Refatoração 1 - Multiplexação de I/O orientada a eventos (selectors / epoll).

Mudanças em relação ao Controlador-v2.py:
  - O laço de polling com busy-wait é substituído por selector.select(), que
    bloqueia no kernel (epoll) até algum socket ficar pronto: CPU ~0% em repouso.
  - O handshake deixa de ser síncrono: vira uma máquina de estados por conexão,
    então N switches negociam em paralelo sem que um bloqueie o outro.
  - recv_exact() é substituído por um buffer por conexão + enquadramento:
    um único recv(64 KiB) pode entregar dezenas de PACKET_IN de uma vez.
  - As respostas são agregadas e enviadas com um único send() por evento.
"""

import os
import selectors
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from of10 import HELLO, FEATURES, OFPT_FEATURES_REPLY, responder, extrair_mensagens

HOST, PORT = '0.0.0.0', int(os.environ.get('OF_PORT', 6653))


class Switch:
    def __init__(self, conn, addr):
        self.conn, self.addr = conn, addr
        self.rbuf, self.wbuf = bytearray(), bytearray()
        self.dpid = None


def main():
    sel = selectors.DefaultSelector()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(128)
    srv.setblocking(False)
    sel.register(srv, selectors.EVENT_READ, None)
    print(f'=== Controlador v3 (selectors/{type(sel).__name__}) em {HOST}:{PORT} ===', flush=True)

    def fechar(sw):
        print(f'[-] Switch {sw.dpid} desconectado', flush=True)
        sel.unregister(sw.conn)
        sw.conn.close()

    while True:
        for key, mask in sel.select():
            if key.data is None:                        # nova conexão
                conn, addr = srv.accept()
                conn.setblocking(False)
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sw = Switch(conn, addr)
                sw.wbuf += HELLO
                sel.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, sw)
                continue

            sw = key.data
            if mask & selectors.EVENT_READ:
                try:
                    dados = sw.conn.recv(65536)
                except (BlockingIOError, InterruptedError):
                    dados = None
                except OSError:
                    dados = b''
                if dados == b'':
                    fechar(sw)
                    continue
                if dados:
                    sw.rbuf += dados
                    for msg_type, xid, body in extrair_mensagens(sw.rbuf):
                        if msg_type == OFPT_FEATURES_REPLY:
                            sw.dpid = FEATURES.unpack_from(body)[0]
                            print(f'[{time.strftime("%H:%M:%S")}] [OK] Handshake com DPID '
                                  f'{sw.dpid}', flush=True)
                        resp = responder(msg_type, xid, body)
                        if resp:
                            sw.wbuf += resp

            if sw.wbuf:
                try:
                    enviados = sw.conn.send(sw.wbuf)
                    del sw.wbuf[:enviados]
                except BlockingIOError:
                    pass
                except OSError:
                    fechar(sw)
                    continue
            # Só pede EVENT_READ se não houver um acúmulo gigante para enviar (backpressure)
            ler = selectors.EVENT_READ if len(sw.wbuf) < 1024 * 1024 else 0
            eventos = ler | (selectors.EVENT_WRITE if sw.wbuf else 0)
            if key.events != eventos:
                sel.modify(sw.conn, eventos, sw)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
