#!/usr/bin/env python3
"""
Figura do Experimento 1: latência de handshake x nº de switches concorrentes.

Entrada: resultados/exp1/latencias.csv (exp1_handshake.py concorrencia)
Saída:   artigo/figuras/exp1_handshake.{pdf,png} e resultados/exp1/resumo.csv
  (a) latência total (1º SYN da rodada -> FEATURES_REPLY), média dos switches;
  (b) maior atraso do HELLO do controlador na rodada (espera na fila de accept/handshake),
      que isola o efeito do controlador do backoff de reconexão do OVS.
"""

import csv
import math
import os
import statistics as st
import sys
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import ESTILO_FIG, FIG, RES, SERIES

ENTRADA = os.path.join(RES, 'exp1', 'latencias.csv')
if not os.path.exists(ENTRADA):
    sys.exit(f'{ENTRADA} não existe: execute "sudo python3 exp1_handshake.py concorrencia"')

rodadas = defaultdict(lambda: {'tot': [], 'hello': [], 'pend': 0, 'syns': 0, 'abort': 0})
for l in csv.DictReader(open(ENTRADA)):
    k = (l['controlador'], int(l['n_switches']), int(l['rodada']))
    d = rodadas[k]
    d['syns'], d['abort'] = int(l['syns']), int(l['conexoes_abortadas'])
    if l['lat_total_ms']:
        d['tot'].append(float(l['lat_total_ms']))
        if l['atraso_hello_ms'] not in ('', 'nan'):
            d['hello'].append(float(l['atraso_hello_ms']))
    else:
        d['pend'] += 1

agg = defaultdict(lambda: defaultdict(list))
for (c, n, _r), d in rodadas.items():
    a = agg[(c, n)]
    if d['tot']:
        a['media'].append(st.mean(d['tot']))
        a['max'].append(max(d['tot']))
    if d['hello']:
        a['hello_max'].append(max(d['hello']))
    a['syns'].append(d['syns'])
    a['abort'].append(d['abort'])
    a['pend'].append(d['pend'])

ns = sorted({n for _, n in agg})
with open(os.path.join(RES, 'exp1', 'resumo.csv'), 'w') as f:
    f.write('controlador,n_switches,rodadas,lat_total_media_ms,dp_ms,lat_total_max_media_ms,'
            'atraso_hello_max_media_ms,syns_medio,abortadas_medio,handshakes_nao_concluidos\n')
    for c, *_ in SERIES:
        for n in ns:
            a = agg.get((c, n))
            if not a or not a['media']:
                continue
            f.write(f"{c},{n},{len(a['media'])},{st.mean(a['media']):.3f},"
                    f"{st.pstdev(a['media']):.3f},{st.mean(a['max']):.3f},"
                    f"{st.mean(a['hello_max']) if a['hello_max'] else float('nan'):.3f},"
                    f"{st.mean(a['syns']):.1f},{st.mean(a['abort']):.1f},{sum(a['pend'])}\n")

plt.rcParams.update(ESTILO_FIG)
fig, eixos = plt.subplots(1, 2, figsize=(9.6, 3.4))
for ax, chave, titulo in ((eixos[0], 'media', '(a) Latência total de handshake'),
                          (eixos[1], 'hello_max', '(b) Maior atraso do HELLO do controlador')):
    valores = []
    for c, rotulo, cor, mk, ls in SERIES:
        xs = [n for n in ns if agg.get((c, n), {}).get(chave)]
        if not xs:
            continue
        ys = [st.mean(agg[(c, n)][chave]) for n in xs]
        dp = [st.pstdev(agg[(c, n)][chave]) for n in xs]
        inf = [min(d, y * 0.9) for y, d in zip(ys, dp)]  # não cruzar zero na escala log
        ax.errorbar(xs, ys, yerr=[inf, dp], color=cor, marker=mk, ls=ls, lw=2, ms=6,
                    capsize=3, elinewidth=1, label=rotulo)
        valores += [y for y in ys if y > 0]
    ax.set_yscale('log')
    if valores:
        ax.set_ylim(10 ** math.floor(math.log10(min(valores))),
                    10 ** math.ceil(math.log10(max(valores) * 2)))
    ax.set_xticks(ns)
    ax.set_xlabel('Switches OpenFlow concorrentes')
    ax.set_ylabel('ms (escala log)')
    ax.set_title(titulo, fontsize=11)
    ax.tick_params(direction='in', which='both', top=True, right=True)
handles, labels = eixos[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=4, fontsize=10,
           frameon=True, edgecolor='#999999')
fig.tight_layout()
for ext in ('pdf', 'png'):
    fig.savefig(os.path.join(FIG, f'exp1_handshake.{ext}'), dpi=300, bbox_inches='tight')
print(open(os.path.join(RES, 'exp1', 'resumo.csv')).read())
