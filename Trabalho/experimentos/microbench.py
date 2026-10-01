#!/usr/bin/env python3
"""Custo (ns) das operações executadas por mensagem PACKET_IN no Controlador-v2."""
import json, os, socket, struct, sys, timeit, io

N = 200_000
hdr = struct.pack('!BBHI', 1, 10, 78, 7)
body = struct.pack('!IHHBx', 0xffffffff, 60, 1, 0) + bytes(60)
S = struct.Struct('!BBHI')
a, b = socket.socketpair()
a.setblocking(False); b.setblocking(False)
msg = hdr + body
buf = io.StringIO()

def ns(stmt, n=N, setup='pass'):
    return min(timeit.repeat(stmt, setup=setup, number=n, repeat=5, globals=globals())) / n * 1e9

def recv_2_chamadas():          # padrão do v2: recv(8) + recv_exact(corpo)
    b.recv(8); b.recv(70)

def recv_1_chamada_lote():       # padrão refatorado: 1 recv traz 64 mensagens
    b.recv(65536)

r = {}
r['struct.unpack(!BBHI) string de formato'] = ns("struct.unpack('!BBHI', hdr)")
r['Struct pré-compilada .unpack_from'] = ns("S.unpack_from(hdr)")
r['struct.unpack(!IHHBx) corpo PACKET_IN'] = ns("struct.unpack('!IHHBx', body[:10])")
r['struct.pack PACKET_OUT (3 chamadas + concat)'] = ns(
    "struct.pack('!BBHI',1,13,94,7)+struct.pack('!IHH',0xffffffff,1,8)+struct.pack('!HHHH',0,8,0xfffb,0)+body[10:]")
r['formatação + print do log por PACKET_IN'] = ns(
    "print(f\"[09:00:00.000] PACKET_IN dpid=1 in_port=1 {body[:6].hex(':')} -> {body[6:12].hex(':')} eth_type=0x0800 len=60\", file=buf)")
def send_recv_v2():
    a.send(msg); recv_2_chamadas()
r['send + 2x recv (enquadramento do v2)'] = ns(send_recv_v2, 100_000)
def lote():
    a.send(msg * 64); recv_1_chamada_lote()
r['send + 1x recv de 64 msgs (por mensagem)'] = ns(lote, 20_000) / 64
def falha_busy():
    try: b.recv(8)
    except BlockingIOError: pass
r['recv() sem dados -> BlockingIOError (1 volta do busy-wait)'] = ns(falha_busy)
for k, v in r.items(): print(f'{v:10.1f} ns  {k}')
json.dump(r, open(os.path.join(os.path.dirname(__file__), '..', 'resultados', 'microbench.json'), 'w'), indent=1, ensure_ascii=False)
