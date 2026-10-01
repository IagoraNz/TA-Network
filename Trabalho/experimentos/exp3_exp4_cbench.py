#!/usr/bin/env python3
"""
Experimentos 3 e 4 com o cbench (não precisa de root nem do Mininet).

Uma única bateria alimenta os dois experimentos, para que o Controlador-v2
(Exp. 3) e as refatorações (Exp. 4) sejam comparados com os MESMOS parâmetros:
  1. CPU em repouso de cada controlador (10 s sem switches);
  2. cbench no modo latência, comando do enunciado
       cbench -c 127.0.0.1 -p 6653 -m 10000 -l 10 -s <S>
     com S em {1, 2, 4, 5, 6, 7, 8, 16} (S = 8 é o caso pedido no enunciado);
  3. cbench no modo throughput (-t) com S em {7, 8}.
Durante cada execução: %CPU do controlador via /proc (monitor.py) e top -b.

Uso:   python3 exp3_exp4_cbench.py [ms_por_laco] [lacos]   (padrão: 10000 10)
Saída: resultados/cbench/cbench.csv        uma linha por execução (RESULT do cbench)
       resultados/cbench/cbench_lacos.csv  vazão de cada laço de teste
       resultados/cbench/cpu_repouso.csv
       resultados/cbench/raw/              saída bruta do cbench, top e logs
"""

import os
import re
import statistics as st
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import CONTROLADORES, PORTA, iniciar_controlador, parar_controlador, pasta
from monitor import MonitorCPU

OUT = pasta('cbench')
RAW = pasta('cbench', 'raw')
NS_LATENCIA = [1, 2, 4, 5, 6, 7, 8, 16]
NS_THROUGHPUT = [7, 8]
DESCARTAR_CPU = 2  # amostras iniciais (0,5 s cada) descartadas da média de CPU


def media_cpu(csv_path):
    linhas = open(csv_path).read().split('\n')[1:]
    v = [float(l.split(',')[1]) for l in linhas if l][DESCARTAR_CPU:]
    return (st.mean(v), max(v)) if v else (float('nan'), float('nan'))


def cpu_repouso():
    with open(os.path.join(OUT, 'cpu_repouso.csv'), 'w') as out:
        out.write('controlador,cpu_media,cpu_max\n')
        for rot, script in CONTROLADORES:
            ctl = iniciar_controlador(script, os.path.join(RAW, f'repouso_{rot}.log'))
            csvp = os.path.join(RAW, f'repouso_{rot}_cpu.csv')
            mon = MonitorCPU([ctl.pid], csvp)
            mon.start()
            time.sleep(10)
            mon.parar.set()
            mon.join()
            parar_controlador(ctl)
            m, mx = media_cpu(csvp)
            out.write(f'{rot},{m:.1f},{mx:.1f}\n')
            print(f'[repouso] {rot:17s} CPU média={m:5.1f}%', flush=True)


def cbench(rot, script, s, ms, lacos, throughput, csv, csv_lacos):
    modo = 'throughput' if throughput else 'latencia'
    nome = f'{rot}_{modo}_s{s}'
    ctl = iniciar_controlador(script, os.path.join(RAW, f'{nome}_controlador.log'))
    csvp = os.path.join(RAW, f'{nome}_cpu.csv')
    mon = MonitorCPU([ctl.pid], csvp)
    mon.start()
    top = subprocess.Popen(['top', '-b', '-d', '1', '-p', str(ctl.pid)],
                           stdout=open(os.path.join(RAW, f'{nome}_top.txt'), 'w'))
    cmd = ['cbench', '-c', '127.0.0.1', '-p', str(PORTA), '-m', str(ms), '-l', str(lacos),
           '-s', str(s)] + (['-t'] if throughput else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=ms / 1000 * lacos + 30)
        txt = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        txt = (e.stdout or b'').decode() + '\n[TIMEOUT]'
    top.terminate()
    top.wait()
    mon.parar.set()
    mon.join()
    parar_controlador(ctl)
    with open(os.path.join(RAW, f'{nome}.txt'), 'w') as f:
        f.write('$ ' + ' '.join(cmd) + '\n' + txt)

    # vazão de cada laço: "... total = 12.3456 per ms" -> resp/s
    for i, v in enumerate(re.findall(r'total = ([\d.]+) per ms', txt), 1):
        csv_lacos.write(f'{rot},{modo},{s},{i},{float(v) * 1000:.1f}\n')
    csv_lacos.flush()

    m = re.search(r'min/max/avg/stdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', txt)
    cpu_m, cpu_x = media_cpu(csvp)
    if m:
        mn, mx, avg, dp = (float(x) for x in m.groups())
        status, erro = 'ok', ''
    else:
        mn = mx = avg = dp = float('nan')
        status = 'falha'
        e = re.search(r'^.*(connect:|returned -1|TIMEOUT).*$', txt, re.M)
        erro = e.group(0).strip().replace(',', ';') if e else ''
    csv.write(f'{rot},{modo},{s},{status},{avg:.1f},{dp:.1f},{mn:.1f},{mx:.1f},'
              f'{cpu_m:.1f},{cpu_x:.1f},{erro}\n')
    csv.flush()
    print(f'[cbench] {rot:17s} {modo:10s} s={s:2d}: {status:5s} {avg:10.0f} resp/s '
          f'(dp {dp:7.0f})  CPU={cpu_m:5.1f}%  {erro}', flush=True)
    time.sleep(1)


def main(ms, lacos):
    cpu_repouso()
    csv = open(os.path.join(OUT, 'cbench.csv'), 'w')
    csv.write('controlador,modo,switches,status,resp_s_media,resp_s_dp,resp_s_min,resp_s_max,'
              'cpu_media,cpu_max,erro\n')
    csv_lacos = open(os.path.join(OUT, 'cbench_lacos.csv'), 'w')
    csv_lacos.write('controlador,modo,switches,laco,resp_s\n')
    for s in NS_LATENCIA:
        for rot, script in CONTROLADORES:
            cbench(rot, script, s, ms, lacos, False, csv, csv_lacos)
    for s in NS_THROUGHPUT:
        for rot, script in CONTROLADORES:
            cbench(rot, script, s, ms, lacos, True, csv, csv_lacos)
    csv.close()
    csv_lacos.close()


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10000,
         int(sys.argv[2]) if len(sys.argv) > 2 else 10)
