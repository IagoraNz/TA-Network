# Primeira Avaliação — Desempenho e exaustão do Controlador-v2 (SDN)

Enunciado: `Primeira avaliacao.pdf`. Entrega: um PDF no modelo SBC (6–10 páginas) com o
link do vídeo (≤ 15 min) na 1ª página.

## Estrutura

```
Controlador-v2.py          controlador base (objeto de estudo, não modificado)
topologia_arvore.py        tree,depth=2,fanout=4 (5 switches, 16 hosts) -> 127.0.0.1:6653
refatoracoes/
  of10.py                  OpenFlow 1.0 comum às refatorações (Structs pré-compiladas, framing)
  Controlador-v3-selectors.py   Refat. 1: multiplexação de I/O (epoll)
  Controlador-v3-threads.py     Refat. 2: uma thread por switch
  Controlador-v3-asyncio.py     Refat. 3: asyncio + fila de eventos limitada por switch
experimentos/
  comum.py                 caminhos, lista de controladores, início seguro do controlador
  monitor.py               %CPU por PID via /proc (mesma métrica do top)
  ambiente.sh              registra hardware/versões -> resultados/ambiente.txt
  exp1_handshake.py        Exp. 1 (root)        -> resultados/exp1/
  exp2_packet_in.py        Exp. 2 (root)        -> resultados/exp2/
  exp3_exp4_cbench.py      Exps. 3 e 4 (cbench) -> resultados/cbench/
  microbench.py            custo (ns) de recv/struct/print por mensagem -> resultados/microbench.json
  grafico_exp{1,2,3,4}.py  figuras -> artigo/figuras/
artigo/                    artigo.tex (esqueleto SBC), referencias.bib, sbc-template.sty, sbc.bst
ferramentas/cbench         binário do cbench usado nos testes
resultados/                dados brutos e resumos (ver abaixo)
```

## Como reproduzir

Antes de qualquer experimento, a porta 6653 precisa estar livre (`ss -ltnp | grep 6653`
não deve mostrar nada). Os scripts verificam isso e abortam se houver outro processo
escutando: foi esse problema que invalidou a execução anterior do Exp. 1.

```bash
cd experimentos
./ambiente.sh                                        # Metodologia

sudo python3 exp1_handshake.py inicializacao 5       # Exp. 1: log do terminal na árvore
sudo python3 exp1_handshake.py concorrencia 5        # Exp. 1: base x refatorações, N=1..16
python3 grafico_exp1.py

sudo python3 exp2_packet_in.py enunciado 30          # Exp. 2: pingall + h1 ping -f h16 + top
sudo python3 exp2_packet_in.py taxa 15               # Exp. 2: curva de saturação (verboso)
python3 grafico_exp2.py verbose

python3 exp3_exp4_cbench.py                          # Exps. 3 e 4 (~70 min, sem root)
python3 grafico_exp3.py
python3 grafico_exp4.py
python3 microbench.py

cd ../artigo && latexmk -pdf artigo.tex
```

## Resultados

| Pasta / arquivo | Conteúdo | Situação |
|---|---|---|
| `ambiente.txt` | hardware e versões | atual |
| `exp1/` | `latencias.csv` (por switch), `resumo.csv`, `pcap/`, `logs/`, `inicializacao_*` | atual |
| `exp2/taxa_verbose_*` | curva de saturação; `_stats.csv` = linhas [STATS] do log; log completo em `.gz` | atual |
| `exp2/enunciado_*` | roteiro exato do enunciado com `top` | atual |
| `microbench.json` | custo (ns) das operações por PACKET_IN | atual |
| `cbench/` | `cbench.csv`, `cbench_lacos.csv`, `cpu_repouso.csv`, `raw/` (saída bruta do cbench e do top) | atual |

Arquivos `exp1c_*`, `exp2esc_*` e `exp4_*` na raiz de `resultados/` são de execuções
anteriores e **não devem ser usados**: no `exp1c`, 90 das 120 rodadas mediram outro processo
(o controlador sob teste falhou com "Address already in use"); o `exp2esc` foi interrompido;
o `exp4` usou parâmetros do cbench diferentes do enunciado.

## Notas para o texto e o vídeo

- O Exp. 2 roda o controlador no modo padrão (verboso); os Exps. 1, 3 e 4 usam `--quiet`.
- Cada ICMP gera ≈ 10 PACKET_IN (o hub inunda e não instala regras): não confunda
  ICMP/s com PACKET_IN/s.
- Com `-s 8`, o Controlador-v2 não completa as conexões do cbench (`listen(5)` +
  handshake síncrono); a vazão máxima deve ser relatada com o maior N que funcionou.
- A 1ª linha `[ERRO] Handshake falhou` ao subir o Mininet é a sonda de porta do Mininet.
- No vídeo: um único `h1 ping -f h16` deixa o controlador em ~23% de CPU (máx. 27% no top),
  porque o `ping -f` é autorregulado pelo RTT (~8,7 ms). Os ~100% só aparecem com ≥ ~3 mil
  ICMP/s em malha aberta (`exp2_packet_in.py taxa`). Para mostrar no top, use injeção
  paralela ou `ping -f -l <N>` (preload). Esta última opção não foi testada: teste antes de gravar.
- Comparação com Ryu/ODL/ONOS: só com valores publicados e citados.
- Exp. 1: a latência total inclui atrasos do próprio OVS em degraus de ~100/500 ms
  (visíveis nas capturas); o atraso do HELLO é a métrica que isola o controlador.
