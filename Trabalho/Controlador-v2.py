#!/usr/bin/env python3
"""
Controlador SDN Didático em Python Puro (OpenFlow 1.0) - Versão 2
Evolução do Controlador-v1: além do handshake (HELLO / FEATURES), o controlador
agora permanece conectado aos switches e processa o plano de controle:
  - OFPT_ECHO_REQUEST  -> OFPT_ECHO_REPLY   (keep-alive do canal OpenFlow)
  - OFPT_PACKET_IN     -> OFPT_PACKET_OUT   (comportamento de HUB: FLOOD)

Arquitetura (propositalmente minimalista):
  - Um único processo e uma única thread.
  - Sockets TCP em modo não-bloqueante varridos em um laço de polling
    (sem select/selectors/asyncio).
  - O handshake de cada switch é feito de forma síncrona, dentro do laço principal.
  - Nenhuma regra (FLOW_MOD) é instalada: TODO pacote gera um PACKET_IN (table-miss).

Prof. Dr. Rayner Gomes Sousa - PPGCC / UFPI (base) | Primeira Avaliação
"""

import os
import socket
import struct
import sys
import time

# Configurações do Servidor Socket
HOST = '0.0.0.0'
PORT = int(os.environ.get('OF_PORT', 6653))  # Porta padrão IANA para OpenFlow

# Imprime uma linha para cada PACKET_IN (didático, porém custoso)
VERBOSE = '--quiet' not in sys.argv

# Definições do Protocolo OpenFlow 1.0
OFP_VERSION = 0x01

# Tipos de Mensagens OpenFlow 1.0 (ofp_type)
OFPT_HELLO = 0
OFPT_ERROR = 1
OFPT_ECHO_REQUEST = 2
OFPT_ECHO_REPLY = 3
OFPT_FEATURES_REQUEST = 5
OFPT_FEATURES_REPLY = 6
OFPT_PACKET_IN = 10
OFPT_PORT_STATUS = 12
OFPT_PACKET_OUT = 13

OFPP_FLOOD = 0xfffb     # Porta virtual: todas as portas exceto a de entrada
OFPAT_OUTPUT = 0        # Ação OUTPUT
NO_BUFFER = 0xffffffff  # Pacote não armazenado no buffer do switch

NOMES = {OFPT_HELLO: 'HELLO', OFPT_ERROR: 'ERROR', OFPT_ECHO_REQUEST: 'ECHO_REQUEST',
         OFPT_ECHO_REPLY: 'ECHO_REPLY', OFPT_FEATURES_REPLY: 'FEATURES_REPLY',
         OFPT_PACKET_IN: 'PACKET_IN', OFPT_PORT_STATUS: 'PORT_STATUS'}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d}] {msg}", flush=True)


def recv_exact(conn, n_bytes):
    """
    Garante o recebimento do número exato de bytes especificado ('n_bytes').
    Como o socket é não-bloqueante, enquanto os bytes não chegam o laço
    fica girando (busy-wait) e consome CPU sem realizar trabalho útil.
    """
    buffer = bytearray()
    while len(buffer) < n_bytes:
        try:
            chunk = conn.recv(n_bytes - len(buffer))
        except BlockingIOError:
            continue
        if not chunk:
            raise ConnectionResetError("Conexão encerrada pelo switch/cliente.")
        buffer.extend(chunk)
    return bytes(buffer)


def parse_header(header_bytes):
    """Decodifica o cabeçalho OpenFlow de 8 bytes ('!BBHI')."""
    return struct.unpack('!BBHI', header_bytes)


def build_header(msg_type, length, xid):
    """Empacota o cabeçalho padrão OpenFlow de 8 bytes."""
    return struct.pack('!BBHI', OFP_VERSION, msg_type, length, xid)


def recv_message(conn):
    """Lê uma mensagem OpenFlow completa (cabeçalho + corpo)."""
    version, msg_type, length, xid = parse_header(recv_exact(conn, 8))
    body = recv_exact(conn, length - 8) if length > 8 else b''
    return msg_type, xid, body


def handshake(conn, addr):
    """
    Handshake OpenFlow síncrono: HELLO <-> HELLO, FEATURES_REQUEST -> FEATURES_REPLY.
    Enquanto este switch não responder, nenhum outro switch é atendido.
    """
    t0 = time.perf_counter()
    conn.sendall(build_header(OFPT_HELLO, 8, 1))

    msg_type, xid, _ = recv_message(conn)
    log(f"    <<< {NOMES.get(msg_type, msg_type)} de {addr[0]}:{addr[1]} (xid={xid})")

    conn.sendall(build_header(OFPT_FEATURES_REQUEST, 8, 100))
    log(f"    >>> FEATURES_REQUEST para {addr[0]}:{addr[1]}")

    while True:
        msg_type, xid, body = recv_message(conn)
        if msg_type == OFPT_FEATURES_REPLY:
            break
        log(f"    <<< {NOMES.get(msg_type, msg_type)} ignorada durante o handshake")

    dpid, n_buffers, n_tables, _pad, capabilities, actions = struct.unpack('!QIB3sII', body[:24])
    num_ports = (len(body) - 24) // 48
    dt = (time.perf_counter() - t0) * 1000
    log(f"    <<< FEATURES_REPLY: DPID={dpid:016x} buffers={n_buffers} "
        f"tabelas={n_tables} portas={num_ports} ({dt:.2f} ms)")
    return dpid


def handle_packet_in(conn, dpid, xid, body):
    """
    Decodifica o PACKET_IN e devolve um PACKET_OUT com ação FLOOD (hub).
    ofp_packet_in: buffer_id(I) total_len(H) in_port(H) reason(B) pad(x) data
    """
    buffer_id, total_len, in_port, reason = struct.unpack('!IHHBx', body[:10])
    data = body[10:]

    if VERBOSE and len(data) >= 14:
        dst, src, eth_type = struct.unpack('!6s6sH', data[:14])
        log(f"PACKET_IN dpid={dpid} in_port={in_port} {src.hex(':')} -> {dst.hex(':')} "
            f"eth_type=0x{eth_type:04x} len={total_len}")

    # ofp_packet_out: buffer_id(I) in_port(H) actions_len(H) + ofp_action_output(8 bytes)
    action = struct.pack('!HHHH', OFPAT_OUTPUT, 8, OFPP_FLOOD, 0)
    payload = data if buffer_id == NO_BUFFER else b''
    length = 8 + 8 + len(action) + len(payload)
    msg = build_header(OFPT_PACKET_OUT, length, xid) + \
        struct.pack('!IHH', buffer_id, in_port, len(action)) + action + payload
    conn.sendall(msg)


def main():
    print("=== Controlador SDN Didático v2 (OpenFlow 1.0 / Hub) ===")
    print(f"Iniciando servidor socket TCP em {HOST}:{PORT}...")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    server_socket.setblocking(False)
    print(f"Aguardando conexões dos switches (porta {PORT})...\n", flush=True)

    switches = []  # lista de [conn, addr, dpid]
    n_pktin = 0
    n_total = 0
    t_stats = time.time()

    while True:
        idle = True
        # ---------------------------------------------------------------
        # 1) Novas conexões: accept + handshake síncrono (um por vez)
        # ---------------------------------------------------------------
        try:
            conn, addr = server_socket.accept()
            conn.setblocking(False)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            log(f"[+] Conexão TCP estabelecida com o switch: {addr[0]}:{addr[1]}")
            idle = False
            try:
                dpid = handshake(conn, addr)
                switches.append([conn, addr, dpid])
                log(f"[OK] Handshake concluído com DPID {dpid} "
                    f"({len(switches)} switch(es) conectado(s))")
            except (ConnectionError, OSError, struct.error) as e:
                log(f"[ERRO] Handshake falhou com {addr}: {e}")
                conn.close()
        except BlockingIOError:
            pass

        # ---------------------------------------------------------------
        # 2) Polling sequencial de cada switch (sem select/selectors)
        # ---------------------------------------------------------------
        for sw in list(switches):
            conn, addr, dpid = sw
            try:
                try:
                    first = conn.recv(8)
                except BlockingIOError:
                    continue
                if not first:
                    raise ConnectionResetError("Conexão encerrada pelo switch.")
                idle = False
                header = first + recv_exact(conn, 8 - len(first)) if len(first) < 8 else first
                version, msg_type, length, xid = parse_header(header)
                body = recv_exact(conn, length - 8) if length > 8 else b''
                n_total += 1

                if msg_type == OFPT_PACKET_IN:
                    n_pktin += 1
                    handle_packet_in(conn, dpid, xid, body)
                elif msg_type == OFPT_ECHO_REQUEST:
                    conn.sendall(build_header(OFPT_ECHO_REPLY, 8 + len(body), xid) + body)
                elif msg_type == OFPT_PORT_STATUS:
                    pass
                else:
                    log(f"<<< {NOMES.get(msg_type, msg_type)} de DPID {dpid} (ignorada)")
            except (ConnectionError, OSError, struct.error) as e:
                log(f"[-] Switch DPID {dpid} desconectado: {e}")
                conn.close()
                switches.remove(sw)

        # ---------------------------------------------------------------
        # 3) Estatística de vazão a cada 1 segundo e repouso
        # ---------------------------------------------------------------
        if idle:
            time.sleep(0.001)

        now = time.time()
        if now - t_stats >= 1.0:
            log(f"[STATS] switches={len(switches)} packet_in/s={n_pktin / (now - t_stats):.0f} "
                f"msgs/s={n_total / (now - t_stats):.0f}")
            n_pktin = n_total = 0
            t_stats = now


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nControlador finalizado.")
