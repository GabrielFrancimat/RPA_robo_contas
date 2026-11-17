"""Carrega as definições reais do notebook sem executar os exemplos/benchmarks."""
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def carregar(base, porta=0, notebook=None):
    modulo = types.ModuleType('mba_runtime_testes')
    sys.modules[modulo.__name__] = modulo
    ns = modulo.__dict__
    ns['display'] = lambda *args, **kwargs: None
    cells = json.loads(Path(notebook or ROOT / 'RPA_Contas_a_Pagar_Resolvido.ipynb').read_text())['cells']
    fontes = [''.join(c['source']) for c in cells if c['cell_type'] == 'code']
    selecoes = [
        ('CONFIGURAÇÃO DO ROBÔ', None), ('CNPJ: geração', None),
        ('Massa de dados:', None), ('Gerar os PDFs', '# Limpa a'),
        ('Mini-ERP legado', None), ('Exceções e modelo', '# Teste com'),
        ('Validações de negócio', '# Mini'), ('Camada de UI', None),
    ]
    for marcador, fim in selecoes:
        fonte = next(s for s in fontes if marcador in s[:250])
        if fim:
            fonte = fonte.split(fim)[0]
        if marcador == 'CONFIGURAÇÃO DO ROBÔ':
            fonte = fonte.replace('BASE           = Path("lab_rpa")', f'BASE = Path({str(base)!r})')
            fonte = fonte.replace('"127.0.0.1", 8765', f'"127.0.0.1", {porta}')
        exec(compile(fonte, f'<notebook:{marcador}>', 'exec'), ns)
        if marcador == 'Mini-ERP legado':
            ns['ERP_PORTA'] = ns['SERVIDOR_ERP'].server_address[1]
            ns['ERP_URL'] = f"http://127.0.0.1:{ns['ERP_PORTA']}"
    # Classificação definida depois do mini teste da célula de regras.
    regras = next(s for s in fontes if 'Validações de negócio' in s[:250])
    if '# Mini' in regras:
        exec('import unicodedata' + regras.split('import unicodedata', 1)[1], ns)
    fonte_orq = next(s for s in fontes if '@dataclass\nclass Resultado' in s)
    exec(fonte_orq.split('\nresultados = rodar')[0], ns)
    fonte_email = next(s for s in fontes if 'from email.message import EmailMessage' in s)
    exec(fonte_email.split('\narquivo_email =')[0], ns)
    return modulo
