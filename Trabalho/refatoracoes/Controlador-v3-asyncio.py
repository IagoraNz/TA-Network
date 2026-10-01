#!/usr/bin/env python3
"""
Refatoração 3 - Corrotinas assíncronas (asyncio) + fila de eventos por switch.

Mudanças em relação ao Controlador-v2.py:
  - Cada switch é atendido por corrotinas; 'await reader.read()' devolve o
    controle ao event loop enquanto não há dados (modelo semelhante ao do Ryu,
    que usa green threads do eventlet).
  - Separação entre I/O e lógica: a corrotina leitora publica os lotes de
    mensagens decodificadas em uma asyncio.Queue LIMITADA, consumida por um
    despachante do mesmo switch. A fila limitada aplica backpressure (a leitura
    pausa se o processamento atrasar) e, por ser por switch, um switch lento não
    bloqueia os demais (sem head-of-line blocking entre switches).
  - writer.drain() só é aguardado quando o buffer de saída passa de 1 MiB, em
    vez de a cada lote.
  - Se o pacote uvloop estiver instalado, o event loop passa a ser escrito em C;
    sem ele (caso dos experimentos), usa-se o loop padrão do asyncio.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from of10 import HELLO, FEATURES, OFPT_FEATURES_REPLY, responder, extrair_mensagens

HOST, PORT = '0.0.0.0', int(os.environ.get('OF_PORT', 6653))
LIMITE_FILA = 64               # lotes pendentes por switch
LIMITE_SAIDA = 1024 * 1024     # bytes no buffer de envio antes de aguardar drain()


async def despachante(fila, writer):
    """Consome os lotes de um switch e envia as respostas."""
    while True:
        lote = await fila.get()
        saida = bytearray()
        for msg_type, xid, body in lote:
            if msg_type == OFPT_FEATURES_REPLY:
                dpid = FEATURES.unpack_from(body)[0]
                print(f'[{time.strftime("%H:%M:%S")}] [OK] Handshake com DPID {dpid}', flush=True)
            resp = responder(msg_type, xid, body)
            if resp:
                saida += resp
        if saida and not writer.is_closing():
            writer.write(saida)
            if writer.transport.get_write_buffer_size() > LIMITE_SAIDA:
                await writer.drain()


async def atender_switch(reader, writer):
    writer.write(HELLO)
    fila = asyncio.Queue(maxsize=LIMITE_FILA)
    tarefa = asyncio.create_task(despachante(fila, writer))
    buf = bytearray()
    try:
        while True:
            dados = await reader.read(65536)
            if not dados:
                break
            buf += dados
            lote = extrair_mensagens(buf)
            if lote:
                await fila.put(lote)
    except ConnectionError:
        pass
    finally:
        tarefa.cancel()
        writer.close()


async def main():
    srv = await asyncio.start_server(atender_switch, HOST, PORT, backlog=128)
    print(f'=== Controlador v3 (asyncio) em {HOST}:{PORT} ===', flush=True)
    async with srv:
        await srv.serve_forever()


if __name__ == '__main__':
    try:
        try:
            import uvloop
            uvloop.run(main())
        except ImportError:
            asyncio.run(main())
    except KeyboardInterrupt:
        pass
