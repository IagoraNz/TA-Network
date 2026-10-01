"""Funções OpenFlow 1.0 compartilhadas pelas versões refatoradas do controlador."""

import struct

OFP_VERSION = 0x01
OFPT_HELLO = 0
OFPT_ECHO_REQUEST = 2
OFPT_ECHO_REPLY = 3
OFPT_FEATURES_REQUEST = 5
OFPT_FEATURES_REPLY = 6
OFPT_PACKET_IN = 10
OFPT_PACKET_OUT = 13
OFPP_FLOOD = 0xfffb
NO_BUFFER = 0xffffffff

# Structs pré-compiladas: organizam os formatos em um só lugar. O ganho de desempenho é
# desprezível, pois o módulo struct já mantém um cache das strings de formato
# (microbench.py: ~140 ns contra ~130 ns por unpack); o que pesa por mensagem são as
# syscalls e o print (ver resultados/microbench.json).
HEADER = struct.Struct('!BBHI')
PACKET_IN = struct.Struct('!IHHBx')
PACKET_OUT = struct.Struct('!BBHIIHH')
FEATURES = struct.Struct('!QIB3sII')
ACTION_FLOOD = struct.pack('!HHHH', 0, 8, OFPP_FLOOD, 0)

HELLO = HEADER.pack(OFP_VERSION, OFPT_HELLO, 8, 1)
FEATURES_REQUEST = HEADER.pack(OFP_VERSION, OFPT_FEATURES_REQUEST, 8, 100)


def packet_out(xid, body):
    """Monta o PACKET_OUT (FLOOD) correspondente ao corpo de um PACKET_IN."""
    buffer_id, _total_len, in_port, _reason = PACKET_IN.unpack_from(body)
    payload = body[10:] if buffer_id == NO_BUFFER else b''
    return PACKET_OUT.pack(OFP_VERSION, OFPT_PACKET_OUT, 24 + len(payload), xid,
                           buffer_id, in_port, 8) + ACTION_FLOOD + payload


def responder(msg_type, xid, body):
    """Resposta do controlador para uma mensagem recebida (ou None)."""
    if msg_type == OFPT_PACKET_IN:
        return packet_out(xid, body)
    if msg_type == OFPT_ECHO_REQUEST:
        return HEADER.pack(OFP_VERSION, OFPT_ECHO_REPLY, 8 + len(body), xid) + body
    if msg_type == OFPT_HELLO:
        return FEATURES_REQUEST
    return None


def extrair_mensagens(buf):
    """
    Enquadramento (framing) sobre um bytearray acumulado: devolve as mensagens
    completas e remove-as do buffer. Uma única chamada recv() pode trazer
    dezenas de mensagens, reduzindo o número de syscalls por mensagem.
    """
    msgs = []
    pos, n = 0, len(buf)
    while n - pos >= 8:
        _v, msg_type, length, xid = HEADER.unpack_from(buf, pos)
        if n - pos < length:
            break
        msgs.append((msg_type, xid, bytes(buf[pos + 8:pos + length])))
        pos += length
    del buf[:pos]
    return msgs
