#!/usr/bin/env python3
"""
Figuras do Experimento 4: Controlador-v2 (base) x 3 refatorações no cbench.

Entrada: resultados/cbench/{cbench.csv, cpu_repouso.csv} (exp3_exp4_cbench.py)
Saída:   artigo/figuras/
  exp4_vazao_cbench  vazão x nº de switches (modo latência, comando do enunciado);
  exp4_cpu           %CPU em repouso e sob carga, com o MESMO nº de switches para
                     todos (o maior em que o base ainda funciona);
  exp4_throughput    vazão no modo throughput (-t).
"""

import csv
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import ESTILO_FIG, FIG, RES, SERIES

DIR = os.path.join(RES, 'cbench')
if not os.path.exists(os.path.join(DIR, 'cbench.csv')):
    sys.exit('resultados/cbench/cbench.csv não existe: execute "python3 exp3_exp4_cbench.py"')
plt.rcParams.update(ESTILO_FIG)
CURTO = {'base': 'Base', 'refat1_selectors': 'Refat. 1\nselectors',
         'refat2_threads': 'Refat. 2\nthreads', 'refat3_asyncio': 'Refat. 3\nasyncio'}

dados = list(csv.DictReader(open(os.path.join(DIR, 'cbench.csv'))))
repouso = {r['controlador']: float(r['cpu_media'])
           for r in csv.DictReader(open(os.path.join(DIR, 'cpu_repouso.csv')))}
lat = [r for r in dados if r['modo'] == 'latencia']
thr = [r for r in dados if r['modo'] == 'throughput']
ns = sorted({int(r['switches']) for r in lat})


def salvar(fig, nome):
    fig.tight_layout()
    for ext in ('pdf', 'png'):
        fig.savefig(os.path.join(FIG, f'{nome}.{ext}'), dpi=300, bbox_inches='tight')
    plt.close(fig)


def legenda(ax, ncol=2):
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.02), ncol=ncol, fontsize=10,
              frameon=True, edgecolor='#999999', handlelength=2.6)


# ---------------------------------------------------------------- vazão x switches
fig, ax = plt.subplots(figsize=(5.6, 3.6))
for c, rot, cor, mk, ls in SERIES:
    pts = sorted((int(r['switches']), r) for r in lat if r['controlador'] == c)
    ok = [(n, float(r['resp_s_media']) / 1000, float(r['resp_s_dp']) / 1000)
          for n, r in pts if r['status'] == 'ok']
    ax.errorbar([p[0] for p in ok], [p[1] for p in ok], yerr=[p[2] for p in ok], color=cor,
                marker=mk, ls=ls, lw=2, ms=6, capsize=3, elinewidth=1, label=rot)
    falhas = [n for n, r in pts if r['status'] != 'ok']
    if falhas:
        ax.scatter(falhas, [0] * len(falhas), marker='X', s=90, color=cor, zorder=5, clip_on=False)
        ax.annotate('falha de conexão', (falhas[0], 0), xytext=(0, 60), textcoords='offset points',
                    ha='center', fontsize=8.5, color=cor, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec=cor, lw=0.8),
                    arrowprops=dict(arrowstyle='-', color=cor, lw=0.8))
ax.set_xscale('log', base=2)
ax.set_xticks(ns)
ax.set_xticklabels([str(n) for n in ns])
ax.set_ylim(bottom=0)
ax.set_xlabel('Switches emulados pelo cbench (-s)')
ax.set_ylabel('Vazão (mil respostas/s)')
ax.tick_params(direction='in', which='both', top=True, right=True)
legenda(ax)
salvar(fig, 'exp4_vazao_cbench')

# ---------------------------------------------------------------- CPU repouso x carga
base_ok = [int(r['switches']) for r in lat if r['controlador'] == 'base' and r['status'] == 'ok']
s_ref = max(base_ok) if base_ok else min(ns)
fig, ax = plt.subplots(figsize=(5.6, 3.2))
larg = 0.38
for i, (c, rot, cor, mk, ls) in enumerate(SERIES):
    carga = next((r for r in lat if r['controlador'] == c and int(r['switches']) == s_ref), None)
    cpu_carga = float(carga['cpu_media']) if carga else math.nan
    ax.bar(i - larg / 2, repouso.get(c, math.nan), width=larg - 0.04, color=cor, alpha=0.35,
           edgecolor=cor, hatch='//', label='Repouso (sem switches)' if i == 0 else None)
    ax.bar(i + larg / 2, cpu_carga, width=larg - 0.04, color=cor,
           label=f'Sob carga (cbench, s={s_ref})' if i == 0 else None)
    ax.text(i - larg / 2, repouso.get(c, 0) + 3, f'{repouso.get(c, math.nan):.0f}', ha='center',
            fontsize=9)
    ax.text(i + larg / 2, cpu_carga + 3, f'{cpu_carga:.0f}', ha='center', fontsize=9)
ax.set_xticks(range(len(SERIES)), [CURTO[c] for c, *_ in SERIES], fontsize=9.5)
ax.set_ylim(0, max(110, max(float(r['cpu_media']) for r in lat) * 1.15))
ax.set_ylabel('CPU (% de 1 núcleo)')
ax.tick_params(direction='in', which='both', right=True)
legenda(ax)
salvar(fig, 'exp4_cpu')

# ---------------------------------------------------------------- modo throughput
if thr:
    sws = sorted({int(r['switches']) for r in thr})
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    larg = 0.8 / len(SERIES)
    for i, (c, rot, cor, mk, ls) in enumerate(SERIES):
        for j, s in enumerate(sws):
            r = next((x for x in thr if x['controlador'] == c and int(x['switches']) == s), None)
            if r is None:
                continue
            x = j + (i - (len(SERIES) - 1) / 2) * larg
            if r['status'] == 'ok':
                ax.bar(x, float(r['resp_s_media']) / 1e6, width=larg * 0.92, color=cor,
                       yerr=float(r['resp_s_dp']) / 1e6, capsize=2, label=rot if j == 0 else None)
            else:
                ax.bar(x, 0, width=larg * 0.92, color=cor, label=rot if j == 0 else None)
                ax.text(x, 0.02, 'falha', rotation=90, ha='center', va='bottom', fontsize=8.5,
                        color=cor, fontweight='bold')
    ax.set_xticks(range(len(sws)), [f'{s} switches' for s in sws])
    ax.set_ylabel('Vazão (milhões de resp/s)')
    ax.set_ylim(bottom=0)
    ax.tick_params(direction='in', which='both', right=True)
    legenda(ax)
    salvar(fig, 'exp4_throughput')

print('controlador        modo        s  status        resp/s        dp   CPU%')
for r in dados:
    print(f"{r['controlador']:18s} {r['modo']:10s} {int(r['switches']):2d} {r['status']:6s} "
          f"{float(r['resp_s_media']):12.0f} {float(r['resp_s_dp']):9.0f} {float(r['cpu_media']):6.1f}")
print('CPU em repouso:', repouso, f'| CPU sob carga comparada em s={s_ref}')
