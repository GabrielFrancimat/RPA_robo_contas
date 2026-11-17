"""Executa em kernel limpo e salva saídas inclusive em caso de falha."""
from pathlib import Path
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
import sys

root = Path(__file__).resolve().parents[1]
caminho = root / 'RPA_Contas_a_Pagar_Resolvido.ipynb'
nb = nbformat.read(caminho, as_version=4)
km = KernelManager(kernel_name='python3')
# Usa explicitamente o Python do ambiente que invocou este script.
km.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
client = NotebookClient(nb, km=km, timeout=240, resources={'metadata': {'path': str(root)}},
    on_cell_start=lambda cell, cell_index: print(f'Célula {cell_index}: {cell.cell_type}', flush=True))
try:
    client.execute()
finally:
    nbformat.write(nb, caminho)
print('Notebook executado sem erros:', caminho)
