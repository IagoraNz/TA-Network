#!/usr/bin/env python3
"""
Experimento 1: handshake OpenFlow com múltiplas conexões (executar como root).

  sudo python3 exp1_handshake.py inicializacao [rodadas]
      Cenário do enunciado: Controlador-v2 (modo verboso, como no vídeo) é iniciado
      e, em seguida, a topologia tree,depth=2,fanout=4 (5 switches). Grava o log do
      terminal do controlador e o tempo até os 5 switches ficarem conectados.

  sudo python3 exp1_handshake.py concorrencia [rodadas] [N,N,...] [controlador,...]
      Comparativo base x refatorações. Para cada N em {1, 2, 4, 5, 8, 16}:
        1. N switches OVS (OpenFlow 1.0) são criados SEM controlador
           (N = 5: tree,depth=2,fanout=4; demais N: switches em cadeia linear;
           a topologia do plano de dados não interfere no handshake);
        2. o controlador sob teste é iniciado (abortando se a porta já estiver ocupada);
        3. tcpdump captura a porta 6653 e uma única transação ovs-vsctl aponta os N
           switches para o controlador (conexões simultâneas);
        4. aguarda-se is_connected=true em todos (limite de 30 s).
      Métricas por switch, extraídas da captura:
        lat_total_ms    1º SYN da rodada -> FEATURES_REPLY do switch (inclui reconexões
                        e o backoff do OVS após conexões abortadas);
        lat_conexao_ms  SYN da conexão que teve sucesso -> FEATURES_REPLY;
        atraso_hello_ms SYN dessa conexão -> 1º byte enviado pelo controlador (HELLO):
                        mede quanto tempo a conexão esperou na fila de accept/handshake.
      Por rodada: total de SYNs e de conexões abortadas pelo switch (FIN/RST antes
      do FEATURES_REPLY), que indicam timeout do lado do OVS.

Saída: resultados/exp1/
"""

import os
import struct
import subprocess
import sys
import time
from functools import partial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from mininet.clean import cleanup
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.topo import Topo
from mininet.topolib import TreeTopo

from comum import CONTROLADORES, PORTA, iniciar_controlador, parar_controlador, pasta
from topologia_arvore import criar_rede

OUT = pasta('exp1')
PCAP_DIR = pasta('exp1', 'pcap')
LOGS = pasta('exp1', 'logs')
NS = [1, 2, 4, 5, 8, 16]
LIMITE = 30.0
OFPT_FEATURES_REPLY = 6


class Linear(Topo):
    """N switches em cadeia, cada um com um host."""

    def build(self, n=1):
        anterior = None
        for i in range(1, n + 1):
            s = self.addSwitch(f's{i}', dpid=f'{i:016x}')
            self.addLink(self.addHost(f'h{i}'), s)
            if anterior:
                self.addLink(anterior, s)
            anterior = s


def topologia(n):
    return (TreeTopo(depth=2, fanout=4), 'tree') if n == 5 else (Linear(n=n), 'linear')


# ------------------------------------------------------------------ captura
def ler_pcap(path):
    """
    Devolve (t_syn0, conexoes, n_syn) onde conexoes[porta_origem] = dict com
    syn, hello (1º payload do controlador), features, dpid, fim (FIN/RST do switch).
    """
    dados = open(path, 'rb').read()
    if len(dados) < 24:
        return None, {}, 0
    magic = struct.unpack_from('<I', dados)[0]
    fmt = '<' if magic in (0xa1b2c3d4, 0xa1b23c4d) else '>'
    nano = magic in (0xa1b23c4d, 0x4d3cb2a1)
    pos, t_syn0, n_syn = 24, None, 0
    con, bufs = {}, {}
    while pos + 16 <= len(dados):
        seg, frac, incl, _ = struct.unpack_from(fmt + 'IIII', dados, pos)
        pkt = dados[pos + 16:pos + 16 + incl]
        pos += 16 + incl
        t = seg + frac / (1e9 if nano else 1e6)
        if len(pkt) < 34 or pkt[12:14] != b'\x08\x00':
            continue
        tcp = 14 + (pkt[14] & 0x0f) * 4
        sport, dport = struct.unpack_from('!HH', pkt, tcp)
        flags = pkt[tcp + 13]
        payload = pkt[tcp + (pkt[tcp + 12] >> 4) * 4:]
        if dport == PORTA:                                   # switch -> controlador
            if flags & 0x02 and not flags & 0x10:            # SYN
                n_syn += 1
                t_syn0 = t if t_syn0 is None else min(t_syn0, t)
                con[sport] = {'syn': t, 'hello': None, 'features': None, 'dpid': None,
                              'fim': None}
                bufs[sport] = bytearray()
                continue
            c = con.get(sport)
            if c is None:
                continue
            if flags & 0x05 and c['fim'] is None:            # FIN ou RST
                c['fim'] = t
            buf = bufs[sport]
            buf += payload
            while len(buf) >= 8:
                _v, tipo, tam, _x = struct.unpack_from('!BBHI', buf)
                if tam < 8 or len(buf) < tam:
                    break
                if tipo == OFPT_FEATURES_REPLY and tam >= 16 and c['features'] is None:
                    c['features'] = t
                    c['dpid'] = struct.unpack_from('!Q', buf, 8)[0]
                del buf[:tam]
        elif sport == PORTA and payload:                     # controlador -> switch
            c = con.get(dport)
            if c is not None and c['hello'] is None:
                c['hello'] = t
    return t_syn0, con, n_syn


def esperar_tcpdump(dump):
    for linha in dump.stderr:  # termina se o tcpdump morrer (EOF)
        if 'listening on' in linha:
            return
    raise RuntimeError('tcpdump não iniciou a captura')


# ------------------------------------------------------------------ concorrência
def rodada(net, n, topo, rotulo, script, r, csv, tentativa=1):
    ctl = iniciar_controlador(script, os.path.join(LOGS, f'{rotulo}_n{n}_r{r}.log'))
    pcap = os.path.join(PCAP_DIR, f'{rotulo}_n{n}_r{r}.pcap')
    dump = subprocess.Popen(['tcpdump', '-i', 'lo', '-U', '-n', '-s', '0', '-w', pcap,
                             f'tcp port {PORTA}'], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True)
    esperar_tcpdump(dump)

    cmd = ['ovs-vsctl']
    for sw in net.switches:
        cmd += ['--', 'set-controller', sw.name, f'tcp:127.0.0.1:{PORTA}']
    t_cmd = time.time()
    subprocess.run(cmd, check=True)
    while time.time() - t_cmd < LIMITE:
        out = subprocess.run(['ovs-vsctl', '--columns=is_connected', 'list', 'controller'],
                             capture_output=True, text=True).stdout
        if out.count('true') >= n:
            break
        time.sleep(0.1)
    time.sleep(0.5)

    dump.terminate()
    dump.wait()
    cmd = ['ovs-vsctl']
    for sw in net.switches:
        cmd += ['--', 'del-controller', sw.name]
    subprocess.run(cmd)
    parar_controlador(ctl)

    t0, con, n_syn = ler_pcap(pcap)
    if n_syn < n and tentativa < 3:
        print(f'[exp1] {rotulo} N={n} r={r}: captura incompleta (SYNs={n_syn}), repetindo',
              flush=True)
        time.sleep(1)
        return rodada(net, n, topo, rotulo, script, r, csv, tentativa + 1)

    abortadas = sum(1 for c in con.values() if c['features'] is None and c['fim'] is not None)
    ok = {c['dpid']: c for c in con.values() if c['dpid'] is not None}
    lat = []
    for dpid in range(1, n + 1):
        c = ok.get(dpid)
        if c:
            tot, conx = (c['features'] - t0) * 1000, (c['features'] - c['syn']) * 1000
            hello = (c['hello'] - c['syn']) * 1000 if c['hello'] else float('nan')
            lat.append(tot)
            csv.write(f'{rotulo},{n},{topo},{r},{dpid},{tot:.3f},{conx:.3f},{hello:.3f},'
                      f'{n_syn},{abortadas}\n')
        else:
            csv.write(f'{rotulo},{n},{topo},{r},{dpid},,,,{n_syn},{abortadas}\n')
    csv.flush()
    media = sum(lat) / len(lat) if lat else float('nan')
    print(f'[exp1] {rotulo:17s} N={n:2d} r={r}: {len(lat)}/{n} handshakes, '
          f'lat. total média={media:8.1f} ms, SYNs={n_syn}, abortadas={abortadas}', flush=True)
    time.sleep(0.5)


def concorrencia(rodadas, ns=NS, filtro=None):
    path = os.path.join(OUT, 'latencias.csv')
    anexar = filtro is not None and os.path.exists(path)
    csv = open(path, 'a' if anexar else 'w')
    if not anexar:
        csv.write('controlador,n_switches,topologia,rodada,dpid,lat_total_ms,lat_conexao_ms,'
                  'atraso_hello_ms,syns,conexoes_abortadas\n')
    for n in ns:
        cleanup()
        topo, nome = topologia(n)
        net = Mininet(topo=topo, controller=None, switch=partial(OVSSwitch, protocols='OpenFlow10'))
        net.start()
        for r in range(1, rodadas + 1):
            for rotulo, script in CONTROLADORES:
                if filtro and rotulo not in filtro:
                    continue
                rodada(net, n, nome, rotulo, script, r, csv)
        net.stop()
    csv.close()


# ------------------------------------------------------------------ inicialização
def conectados(net):
    return sum(sw.cmd(f'ovs-vsctl --timeout=2 get controller {sw.name} is_connected').strip()
               == 'true' for sw in net.switches)


def inicializacao(rodadas):
    """Controlador-v2 verboso + Mininet com a árvore do enunciado; log = terminal do controlador."""
    with open(os.path.join(OUT, 'inicializacao_resumo.csv'), 'w') as resumo:
        resumo.write('rodada,t_todos_conectados_s,switches_conectados\n')
        for r in range(1, rodadas + 1):
            cleanup()
            ctl = iniciar_controlador('Controlador-v2.py',
                                      os.path.join(OUT, f'inicializacao_r{r}_controlador.log'),
                                      extra=())
            net = criar_rede()
            t0 = time.time()
            net.start()
            t_ok, n = None, 0
            while time.time() - t0 < LIMITE:
                n = conectados(net)
                if n == len(net.switches):
                    t_ok = time.time() - t0
                    break
                time.sleep(0.05)
            print(f'[exp1/inicializacao] rodada {r}: {n}/5 conectados em {t_ok} s', flush=True)
            resumo.write(f'{r},{"" if t_ok is None else f"{t_ok:.3f}"},{n}\n')
            resumo.flush()
            net.stop()
            parar_controlador(ctl)


if __name__ == '__main__':
    setLogLevel('warning')
    modo = sys.argv[1] if len(sys.argv) > 1 else 'concorrencia'
    rodadas = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if modo == 'inicializacao':
        inicializacao(rodadas)
    else:
        concorrencia(rodadas,
                     [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else NS,
                     sys.argv[4].split(',') if len(sys.argv) > 4 else None)
