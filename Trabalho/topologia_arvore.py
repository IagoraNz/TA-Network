#!/usr/bin/env python3
"""
Topologia em árvore (tree, depth=2, fanout=4) -> 5 switches OVS e 16 hosts,
conectados ao Controlador-v2.py (127.0.0.1:6653) usando OpenFlow 1.0.

Uso interativo (vídeo):   sudo python3 topologia_arvore.py
Equivalente via mn:       sudo mn --topo tree,depth=2,fanout=4 \
                               --controller remote,ip=127.0.0.1,port=6653 \
                               --switch ovsk,protocols=OpenFlow10
"""

from functools import partial
from mininet.net import Mininet
from mininet.topolib import TreeTopo
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel


def criar_rede():
    controlador = partial(RemoteController, ip='127.0.0.1', port=6653)
    switch_of10 = partial(OVSSwitch, protocols='OpenFlow10')
    return Mininet(topo=TreeTopo(depth=2, fanout=4), controller=controlador,
                   switch=switch_of10, autoSetMacs=True)


if __name__ == '__main__':
    setLogLevel('info')
    net = criar_rede()
    net.start()
    CLI(net)
    net.stop()
