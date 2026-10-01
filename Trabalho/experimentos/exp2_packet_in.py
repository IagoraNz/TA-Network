#!/usr/bin/env python3
"""
Experimento 2: estresse de table-miss via PACKET_IN (executar como root).

  sudo python3 exp2_packet_in.py enunciado [duracao_s]
      Roteiro exato do enunciado com o Controlador-v2 no modo padrão (verboso):
      10 s ocioso -> pingall -> h1 ping -f h16 (duracao_s, padrão 30) -> ping de
      verificação. Coleta %CPU (top -b e /proc), saídas dos pings, nº de switches
      conectados e eventos de desconexão no log do OVS.

  sudo python3 exp2_packet_in.py taxa [duracao_s] [--quiet]
      Curva de saturação: patamares de taxa fixa de ICMP echo request (ping -i em
      malha aberta, distribuídos entre os pares hi -> h(17-i)). Por patamar: taxa
      realmente enviada, perda, RTT, %CPU e PACKET_IN/s processados (linhas [STATS]
      do log do controlador).

Observação: cada ICMP gera vários PACKET_IN, pois o controlador é um hub (FLOOD)
sem FLOW_MOD: todo pacote, em cada switch do caminho e nas cópias inundadas,
volta ao controlador. Por isso a taxa de ICMP e a de PACKET_IN são grandezas distintas.

Saída: resultados/exp2/
"""

import gzip
import math
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from mininet.clean import cleanup
from mininet.log import setLogLevel

from comum import iniciar_controlador, parar_controlador, pasta
from monitor import MonitorCPU
from topologia_arvore import criar_rede

OUT = pasta('exp2')
OVS_LOG = '/var/log/openvswitch/ovs-vswitchd.log'
OVS_PID = '/var/run/openvswitch/ovs-vswitchd.pid'
PADROES_DESCONEXAO = r'.*(inactivity probe|disconnect|connection closed|timed out|Connection refused).*'

TAXAS = (200, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 10000, 12000, 15000, 20000)
TAXA_MAX_PROC = 200  # ICMP echo requests/s por processo ping (-i >= 5 ms)


def conectados(net):
    return sum(sw.cmd(f'ovs-vsctl --timeout=2 get controller {sw.name} is_connected').strip()
               == 'true' for sw in net.switches)


def subir_rede(log_ctl, extra):
    cleanup()
    ctl = iniciar_controlador('Controlador-v2.py', log_ctl, extra)
    net = criar_rede()
    net.start()
    t0 = time.time()
    while conectados(net) < len(net.switches) and time.time() - t0 < 30:
        time.sleep(0.1)
    print(f'[exp2] {conectados(net)}/5 switches conectados', flush=True)
    return ctl, net


def offset_log_ovs():
    return os.path.getsize(OVS_LOG) if os.path.exists(OVS_LOG) else 0


def trecho_log_ovs(offset):
    if not os.path.exists(OVS_LOG):
        return ''
    with open(OVS_LOG, errors='replace') as f:
        f.seek(offset)
        return f.read()


def extrair_stats(log_ctl, csv_path):
    """Copia as linhas [STATS] do log do controlador para um CSV pequeno."""
    padrao = re.compile(r'\[(\d\d):(\d\d):(\d\d)\.(\d{3})\] \[STATS\] switches=(\d+) '
                        r'packet_in/s=(\d+) msgs/s=(\d+)')
    with open(log_ctl, errors='replace') as f, open(csv_path, 'w') as out:
        out.write('seg_do_dia,switches,packet_in_s,msgs_s\n')
        for l in f:
            m = padrao.match(l)
            if m:
                h, mi, s, ms, sw, pin, tot = (int(x) for x in m.groups())
                out.write(f'{h * 3600 + mi * 60 + s + ms / 1000:.3f},{sw},{pin},{tot}\n')


def compactar(path):
    """Logs verbosos chegam a centenas de MB: guarda apenas a versão .gz."""
    with open(path, 'rb') as f, gzip.open(path + '.gz', 'wb') as g:
        shutil.copyfileobj(f, g)
    os.remove(path)


def enunciado(duracao):
    off = offset_log_ovs()
    log_ctl = os.path.join(OUT, 'enunciado_controlador.log')
    ctl, net = subir_rede(log_ctl, extra=())
    ovs_pid = int(open(OVS_PID).read())
    mon = MonitorCPU([ctl.pid, ovs_pid], os.path.join(OUT, 'enunciado_cpu.csv'))
    mon.start()
    top = subprocess.Popen(['top', '-b', '-d', '1', '-p', f'{ctl.pid},{ovs_pid}'],
                           stdout=open(os.path.join(OUT, 'enunciado_top.txt'), 'w'))
    h1, h16 = net.get('h1', 'h16')
    saidas = {}

    mon.marcar('ocioso')
    time.sleep(10)
    mon.marcar('pingall')
    t = time.time()
    perda = net.pingAll(timeout='1')
    saidas['pingall'] = f'perda={perda}% duracao={time.time() - t:.2f}s'
    print(f'[exp2] pingall: {saidas["pingall"]}', flush=True)
    mon.marcar('ping -f')
    saidas['ping -f'] = h1.cmd(f'ping -f -w {duracao} {h16.IP()}')
    print(saidas['ping -f'], flush=True)
    mon.marcar('pós-flood')
    saidas['ping de verificação'] = h1.cmd(f'ping -c 10 -i 0.2 {h16.IP()}')
    time.sleep(5)
    mon.marcar('fim')
    saidas['switches conectados ao final'] = str(conectados(net))

    mon.parar.set()
    mon.join()
    top.terminate()
    top.wait()
    with open(os.path.join(OUT, 'enunciado_saidas.txt'), 'w') as f:
        for k, v in saidas.items():
            f.write(f'===== {k} =====\n{v}\n')
    log_ovs = trecho_log_ovs(off)
    with open(os.path.join(OUT, 'enunciado_ovs_vswitchd.log'), 'w') as f:
        f.write(log_ovs)
    eventos = re.findall(PADROES_DESCONEXAO, log_ovs)
    print(f'[exp2] eventos de desconexão no log do OVS: {len(eventos)}', flush=True)
    net.stop()
    parar_controlador(ctl)
    extrair_stats(log_ctl, os.path.join(OUT, 'enunciado_stats.csv'))
    compactar(log_ctl)


def taxa(duracao, extra=()):
    rot = 'quiet' if '--quiet' in extra else 'verbose'
    off = offset_log_ovs()
    log_ctl = os.path.join(OUT, f'taxa_{rot}_controlador.log')
    ctl, net = subir_rede(log_ctl, extra)
    net.pingAll(timeout='1')
    mon = MonitorCPU([ctl.pid], os.path.join(OUT, f'taxa_{rot}_cpu.csv'))
    mon.start()
    resumo = open(os.path.join(OUT, f'taxa_{rot}_resumo.csv'), 'w')
    resumo.write('taxa_nominal,taxa_enviada,taxa_recebida,processos,transmitidos,recebidos,'
                 'perda_pct,rtt_avg_ms,conectados\n')
    for alvo in TAXAS:
        nproc = math.ceil(alvo / TAXA_MAX_PROC)
        intervalo = nproc / alvo
        mon.marcar(f'taxa {alvo}')
        procs = []
        for k in range(nproc):  # distribui entre os pares hi -> h(17-i), i = 1..8
            i = 1 + k % 8
            o, d = net.get(f'h{i}'), net.get(f'h{17 - i}')
            procs.append(o.popen(['ping', '-q', '-i', f'{intervalo:.5f}', '-w', str(duracao),
                                  d.IP()], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True))
        tx = rx = 0
        rtts = []
        for p in procs:
            out = p.communicate()[0]
            m = re.search(r'(\d+) packets transmitted, (\d+) received', out)
            if m:
                tx, rx = tx + int(m.group(1)), rx + int(m.group(2))
            m = re.search(r'= [\d.]+/([\d.]+)/', out)
            if m:
                rtts.append(float(m.group(1)))
        mon.marcar(f'pausa {alvo}')
        perda = 100.0 * (tx - rx) / tx if tx else 100.0
        rtt = sum(rtts) / len(rtts) if rtts else float('nan')
        n = conectados(net)
        print(f'[exp2/taxa/{rot}] alvo {alvo} req/s ({nproc} pings): enviada={tx / duracao:.0f}/s '
              f'recebida={rx / duracao:.0f}/s perda={perda:.2f}% rtt={rtt:.2f} ms '
              f'conectados={n}', flush=True)
        resumo.write(f'{alvo},{tx / duracao:.1f},{rx / duracao:.1f},{nproc},{tx},{rx},'
                     f'{perda:.3f},{rtt:.3f},{n}\n')
        resumo.flush()
        time.sleep(3)
    mon.marcar('fim')
    mon.parar.set()
    mon.join()
    resumo.close()
    with open(os.path.join(OUT, f'taxa_{rot}_ovs_vswitchd.log'), 'w') as f:
        f.write(trecho_log_ovs(off))
    net.stop()
    parar_controlador(ctl)
    extrair_stats(log_ctl, os.path.join(OUT, f'taxa_{rot}_stats.csv'))
    compactar(log_ctl)


if __name__ == '__main__':
    setLogLevel('warning')
    modo = sys.argv[1] if len(sys.argv) > 1 else 'enunciado'
    if modo == 'taxa':
        taxa(int(sys.argv[2]) if len(sys.argv) > 2 else 15, tuple(sys.argv[3:]))
    else:
        enunciado(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
