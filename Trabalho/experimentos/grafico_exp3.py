#!/usr/bin/env python3
"""
Figura do Experimento 3: vazão bruta do Controlador-v2 no cbench (somente dados medidos).

Entrada: resultados/cbench/{cbench.csv, cbench_lacos.csv} (exp3_exp4_cbench.py)
Saída:   artigo/figuras/exp3_cbench.{pdf,png}
  (a) vazão de cada laço de 10 s (o 1º laço é aquecimento e é descartado, como no
      RESULT do cbench) para cada nº de switches emulados;
  (b) vazão média +- desvio-padrão e %CPU do controlador x nº de switches; execuções
      em que o cbench não conseguiu conectar são marcadas como falha.

A comparação com Ryu, OpenDaylight e ONOS deve ser feita no texto com valores
publicados e citados, nunca com curvas simuladas.
"""

import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import ESTILO_FIG, FIG, RES

DIR = os.path.join(RES, 'cbench')
if not os.path.exists(os.path.join(DIR, 'cbench.csv')):
    sys.exit('resultados/cbench/cbench.csv não existe: execute "python3 exp3_exp4_cbench.py"')
MS_POR_LACO = 10  # s (-m 10000)
CORES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#c21fc2', '#138a13', '#555555', '#a50f15']
plt.rcParams.update(ESTILO_FIG)

execs = [r for r in csv.DictReader(open(os.path.join(DIR, 'cbench.csv')))
         if r['controlador'] == 'base' and r['modo'] == 'latencia']
lacos = defaultdict(list)
for r in csv.DictReader(open(os.path.join(DIR, 'cbench_lacos.csv'))):
    if r['controlador'] == 'base' and r['modo'] == 'latencia' and int(r['laco']) > 1:
        lacos[int(r['switches'])].append((int(r['laco']) * MS_POR_LACO, float(r['resp_s']) / 1000))

fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={'width_ratios': [1.25, 1]})
for i, s in enumerate(sorted(lacos)):
    xs, ys = zip(*sorted(lacos[s]))
    a.plot(xs, ys, color=CORES[i % len(CORES)], marker='o', ms=4, lw=1.6,
           label=f'{s} switch' + ('es' if s > 1 else ''))
falhas = sorted(int(r['switches']) for r in execs if r['status'] != 'ok')  # marcadas em (b)
a.set_ylim(bottom=0)
a.set_xlabel('Tempo de teste (s)')
a.set_ylabel('Vazão (mil respostas/s)')
a.set_title('(a) Vazão por laço do cbench', fontsize=11)
a.legend(fontsize=8.5, ncol=4, frameon=True, edgecolor='#999999', loc='upper center',
         bbox_to_anchor=(0.5, -0.2))
a.tick_params(direction='in', which='both', top=True, right=True)

ok = sorted((int(r['switches']), r) for r in execs if r['status'] == 'ok')
xs = [s for s, _ in ok]
b.bar([str(s) for s in xs], [float(r['resp_s_media']) / 1000 for _, r in ok],
      yerr=[float(r['resp_s_dp']) / 1000 for _, r in ok], color='#e3242b', alpha=0.85,
      capsize=3, label='Vazão média (mil resp/s)')
for s in falhas:
    b.bar(str(s), 0)
    b.text(str(s), 2, 'falha', ha='center', rotation=90, fontsize=9, color='#a50f15',
           fontweight='bold')
b.set_ylabel('Vazão (mil respostas/s)')
b.set_xlabel('Switches emulados (-s)')
b.set_title('(b) Média e CPU do controlador', fontsize=11)
if falhas:
    b.text(0.98, 0.5, 'falha = cbench não\nconectou os switches', transform=b.transAxes,
           ha='right', fontsize=8.5, color='#a50f15')
b2 = b.twinx()
todos = sorted((int(r['switches']), float(r['cpu_media'])) for r in execs)
b2.plot([str(s) for s, _ in todos], [c for _, c in todos], color='#000000', marker='x', ms=7,
        mew=1.5, lw=1.4, ls='--', label='CPU (%)')
b2.set_ylim(0, 110)
b2.set_ylabel('CPU (% de 1 núcleo)')
h1, l1 = b.get_legend_handles_labels()
h2, l2 = b2.get_legend_handles_labels()
b.legend(h1 + h2, l1 + l2, fontsize=8.5, loc='upper left', frameon=True, edgecolor='#999999')
fig.tight_layout()
for ext in ('pdf', 'png'):
    fig.savefig(os.path.join(FIG, f'exp3_cbench.{ext}'), dpi=300, bbox_inches='tight')

print(' s  status        resp/s média        dp   CPU%   erro')
for r in sorted(execs, key=lambda r: int(r['switches'])):
    print(f"{int(r['switches']):2d}  {r['status']:6s} {float(r['resp_s_media']):16.0f} "
          f"{float(r['resp_s_dp']):9.0f} {float(r['cpu_media']):6.1f}   {r['erro']}")
if ok:
    s, r = max(ok, key=lambda x: float(x[1]['resp_s_max']))
    print(f"Maior vazão em um laço: {float(r['resp_s_max']):.0f} resp/s (s={s})")
s8 = os.path.join(DIR, 'raw', 'base_latencia_s8.txt')
if os.path.exists(s8):
    print('\nSaída do terminal com o comando do enunciado (-s 8):\n' + open(s8).read())
