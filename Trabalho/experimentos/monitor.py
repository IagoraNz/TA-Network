"""Amostragem de CPU de um processo via /proc (equivalente ao %CPU do top)."""

import os
import threading
import time

HZ = os.sysconf('SC_CLK_TCK')


def cpu_ticks(pid):
    with open(f'/proc/{pid}/stat') as f:
        campos = f.read().rsplit(')', 1)[1].split()
    return int(campos[11]) + int(campos[12])  # utime + stime


class MonitorCPU(threading.Thread):
    """Grava 'tempo,cpu%' para cada PID em um CSV a cada 'intervalo' segundos."""

    def __init__(self, pids, csv_path, intervalo=0.5):
        super().__init__(daemon=True)
        self.pids, self.csv_path, self.intervalo = pids, csv_path, intervalo
        self.parar = threading.Event()
        self.eventos = []  # (tempo, rótulo) para marcar fases no gráfico
        self.t0 = time.time()  # fixado aqui: marcar() pode ser chamado antes de run()

    def marcar(self, rotulo):
        self.eventos.append((time.time(), rotulo))

    def run(self):
        t0 = self.t0
        ultimo = {p: cpu_ticks(p) for p in self.pids}
        t_ult = time.time()
        with open(self.csv_path, 'w') as f:
            f.write('t,' + ','.join(str(p) for p in self.pids) + '\n')
            while not self.parar.wait(self.intervalo):
                agora = time.time()
                linha = [f'{agora - t0:.2f}']
                for p in self.pids:
                    try:
                        tk = cpu_ticks(p)
                    except FileNotFoundError:
                        tk = ultimo[p]
                    linha.append(f'{100.0 * (tk - ultimo[p]) / HZ / (agora - t_ult):.1f}')
                    ultimo[p] = tk
                t_ult = agora
                f.write(','.join(linha) + '\n')
                f.flush()
        with open(self.csv_path.replace('.csv', '_eventos.csv'), 'w') as f:
            f.write('t,epoch,evento\n')  # t relativo ao início do CSV de CPU; epoch absoluto
            for t, r in self.eventos:
                f.write(f'{t - t0:.2f},{t:.3f},{r}\n')
