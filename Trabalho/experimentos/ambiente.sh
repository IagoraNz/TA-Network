#!/usr/bin/env bash
# Registra hardware e versões de software para a seção de Metodologia do artigo.
# Uso: ./experimentos/ambiente.sh   ->  resultados/ambiente.txt
BASE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$BASE/resultados/ambiente.txt"
mkdir -p "$BASE/resultados"
{
  echo "# Coletado em $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo; echo "## Sistema"
  uname -srmo
  grep PRETTY_NAME /etc/os-release
  grep -qi microsoft /proc/version && echo "Ambiente: WSL2 ($(cat /proc/version))"
  echo; echo "## CPU e memória"
  lscpu | grep -E 'Model name|^CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|MHz'
  free -h | head -2
  echo; echo "## Software"
  echo "Python: $(python3 --version 2>&1)"
  python3 -c 'import sys; print("GIL habilitado:", sys._is_gil_enabled())' 2>/dev/null
  echo "Mininet: $(mn --version 2>&1)"
  ovs-vsctl --version | head -1
  ovs-vswitchd --version 2>/dev/null | head -1
  echo "cbench: $(command -v cbench)"
  echo "tcpdump: $(tcpdump --version 2>&1 | head -1)"
  echo "top: $(top -V 2>&1 | head -1)"
  python3 -c 'import matplotlib; print("matplotlib:", matplotlib.__version__)'
  python3 -c 'import uvloop' 2>/dev/null && echo "uvloop: instalado" || echo "uvloop: não instalado (asyncio usa o loop padrão)"
  echo; echo "## Parâmetros de rede do kernel"
  sysctl net.core.somaxconn net.ipv4.tcp_max_syn_backlog 2>/dev/null
} > "$OUT"
cat "$OUT"
