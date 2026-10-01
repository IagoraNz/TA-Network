#!/usr/bin/env python3
"""
Figuras do Experimento 2.

  python3 grafico_exp2.py [verbose|quiet]

  exp2_ping_flood   (resultados/exp2/enunciado_*): %CPU do controlador e do OVS ao
                    longo do roteiro do enunciado (ocioso, pingall, h1 ping -f h16).
  exp2_saturacao    (resultados/exp2/taxa_<modo>_*): por patamar de taxa de ICMP
                    enviada, %CPU do controlador, perda de pacotes e PACKET_IN/s
                    efetivamente processados (linhas [STATS] do controlador).

Unidades: o eixo x conta ICMP echo requests/s injetados pelos hosts. Como o
controlador é um hub sem FLOW_MOD, cada ICMP gera vários PACKET_IN (um por switch
no caminho, para a requisição e para a resposta, além das cópias inundadas); por
isso o PACKET_IN/s processado é plotado em eixo próprio.
"""

import csv
import os
import statistics as st
import sys
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import ESTILO_FIG, FIG, RES

DIR = os.path.join(RES, 'exp2')
MODO = sys.argv[1] if len(sys.argv) > 1 else 'verbose'
LIMIAR_PERDA = 1.0  # % : critério de saturação = início da perda sustentada
VERMELHO, VINHO, PRETO, AZUL = '#e3242b', '#a50f15', '#000000', '#1f4fe0'
plt.rcParams.update(ESTILO_FIG)


def ler_cpu(path):
    linhas = list(csv.reader(open(path)))
    return [[float(x) for x in l] for l in linhas[1:] if l]


def ler_eventos(path):
    """Devolve [(t_relativo, epoch ou None, rótulo)] (aceita o formato antigo 't,evento')."""
    linhas = list(csv.reader(open(path)))
    if linhas[0] == ['t', 'epoch', 'evento']:
        return [(float(t), float(e), r) for t, e, r in linhas[1:]]
    return [(float(t), None, r) for t, r in linhas[1:]]


def seg_do_dia(epoch):
    lt = time.localtime(epoch)
    return lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec + epoch % 1


def ler_stats(path):
    return [(float(l['seg_do_dia']), float(l['packet_in_s']))
            for l in csv.DictReader(open(path))] if os.path.exists(path) else []


def alinhar(eventos, stats):
    """
    Deslocamento entre o relógio relativo dos eventos e o horário do log do controlador.
    Usa o epoch gravado pelo monitor; nas execuções antigas (sem epoch), estima o
    deslocamento que maximiza o PACKET_IN/s dentro dos patamares e o minimiza nas pausas.
    """
    if eventos[0][1] is not None:
        return seg_do_dia(eventos[0][1]) - eventos[0][0], 'epoch gravado'
    janelas = [(t, eventos[i + 1][0]) for i, (t, _, r) in enumerate(eventos[:-1])
               if r.startswith('taxa ')]

    def score(o):
        s = 0.0
        for ts, v in stats:
            dentro = any(a + o <= ts <= b + o for a, b in janelas)
            s += v if dentro else -v
        return s

    inicio, fim = stats[0][0], stats[-1][0]
    candidatos = [inicio + k * 0.05 for k in range(int((fim - inicio) / 0.05))]
    melhor = max(candidatos, key=score)
    return melhor, 'estimado por correlação (execução sem epoch)'


# ---------------------------------------------------------------- (a) roteiro do enunciado
cpu_path = os.path.join(DIR, 'enunciado_cpu.csv')
if os.path.exists(cpu_path):
    cab = open(cpu_path).readline().strip().split(',')
    amostras = ler_cpu(cpu_path)
    eventos = ler_eventos(os.path.join(DIR, 'enunciado_cpu_eventos.csv'))
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ts = [a[0] for a in amostras]
    ax.plot(ts, [a[1] for a in amostras], color=VERMELHO, lw=1.8, label='Controlador-v2 (Python)')
    if len(cab) > 2:
        ax.plot(ts, [a[2] for a in amostras], color=AZUL, lw=1.4, ls='--', label='ovs-vswitchd')
    for i, (t, _e, r) in enumerate(eventos[:-1]):
        ax.axvline(t, color='#888888', lw=0.8, ls=':')
        ax.text(t + 0.5, 104 if i % 2 == 0 else 92, r, fontsize=8.5, va='bottom')
    ax.set_ylim(0, 115)
    ax.set_xlabel('Tempo (s)')
    ax.set_ylabel('CPU (% de 1 núcleo)')
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.08), ncol=2, fontsize=10,
              frameon=True, edgecolor='#999999')
    ax.tick_params(direction='in', which='both', top=True, right=True)
    fig.tight_layout()
    for ext in ('pdf', 'png'):
        fig.savefig(os.path.join(FIG, f'exp2_ping_flood.{ext}'), dpi=300, bbox_inches='tight')
    plt.close(fig)
    fases = [(r, t, eventos[i + 1][0]) for i, (t, _e, r) in enumerate(eventos[:-1])]
    for r, a, b in fases:
        v = [x[1] for x in amostras if a + 1 <= x[0] <= b - 1]
        if v:
            print(f'[enunciado] {r:12s} CPU controlador média={st.mean(v):5.1f}%  máx={max(v):5.1f}%')
else:
    print(f'{cpu_path} não existe: execute "sudo python3 exp2_packet_in.py enunciado"')

# ---------------------------------------------------------------- (b) curva de saturação
resumo_path = os.path.join(DIR, f'taxa_{MODO}_resumo.csv')
if not os.path.exists(resumo_path):
    sys.exit(f'{resumo_path} não existe: execute "sudo python3 exp2_packet_in.py taxa"')
resumo = list(csv.DictReader(open(resumo_path)))
amostras = ler_cpu(os.path.join(DIR, f'taxa_{MODO}_cpu.csv'))
eventos = ler_eventos(os.path.join(DIR, f'taxa_{MODO}_cpu_eventos.csv'))
janela = {r: t for t, _e, r in eventos}
stats = ler_stats(os.path.join(DIR, f'taxa_{MODO}_stats.csv'))
offset, origem = alinhar(eventos, stats) if stats else (None, '')

linhas = []
for r in resumo:
    alvo = int(r['taxa_nominal'])
    ini, fim = janela[f'taxa {alvo}'] + 1, janela[f'pausa {alvo}'] - 1  # descarta 1 s em cada borda
    cpu = st.mean([a[1] for a in amostras if ini <= a[0] <= fim])
    pin = [v for t, v in stats if ini + offset <= t <= fim + offset] if stats else []
    linhas.append({'enviada': float(r['taxa_enviada']), 'recebida': float(r['taxa_recebida']),
                   'cpu': min(cpu, 100.0), 'perda': float(r['perda_pct']),
                   'pin': st.mean(pin) if pin else float('nan')})

# acima de ~5 mil ICMP/s os próprios hosts não sustentam a taxa nominal: ordena pela enviada
linhas.sort(key=lambda l: l['enviada'])
saturacao = None
for i, l in enumerate(linhas):
    if l['perda'] >= LIMIAR_PERDA:
        saturacao = (linhas[i - 1]['enviada'], l['enviada']) if i else None
        break

x = [l['enviada'] for l in linhas]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.plot(x, [l['cpu'] for l in linhas], color=VERMELHO, marker='o', ms=6, lw=2,
        label='CPU do controlador (%)')
ax.plot(x, [l['perda'] for l in linhas], color=PRETO, marker='x', ms=7, mew=1.5, lw=2, ls='--',
        label='Perda de pacotes ICMP (%)')
ax.set_ylim(-2, 105)
ax.set_xlabel('ICMP echo requests enviados por segundo')
ax.set_ylabel('Percentual (%)')
if saturacao:
    ax.axvspan(*saturacao, color='#fdecec', zorder=0)
    ax.text(sum(saturacao) / 2, 50, 'início\nda perda', ha='center', va='center', fontsize=9,
            color=VINHO, fontweight='bold')
handles, labels = ax.get_legend_handles_labels()
if stats:
    ax2 = ax.twinx()
    ax2.plot(x, [l['pin'] / 1000 for l in linhas], color=AZUL, marker='s', ms=5, lw=1.6, ls=':',
             label='PACKET_IN processados (mil/s)')
    ax2.set_ylabel('PACKET_IN/s (milhares)')
    ax2.set_ylim(bottom=0)
    h2, l2 = ax2.get_legend_handles_labels()
    handles, labels = handles + h2, labels + l2
ax.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=9.5,
          frameon=True, edgecolor='#999999')
ax.tick_params(direction='in', which='both', top=True)
fig.tight_layout()
for ext in ('pdf', 'png'):
    fig.savefig(os.path.join(FIG, f'exp2_saturacao.{ext}'), dpi=300, bbox_inches='tight')
plt.close(fig)

if stats:
    print(f'alinhamento do log do controlador: {origem}')
print(' ICMP/s env.  ICMP/s rec.   CPU%   perda%   PACKET_IN/s')
for l in linhas:
    print(f"{l['enviada']:11.0f} {l['recebida']:12.0f} {l['cpu']:6.1f} {l['perda']:8.2f} {l['pin']:13.0f}")
if saturacao:
    print(f'perda >= {LIMIAR_PERDA}% a partir de {saturacao[1]:.0f} ICMP/s '
          f'(último patamar sem perda relevante: {saturacao[0]:.0f} ICMP/s)')
