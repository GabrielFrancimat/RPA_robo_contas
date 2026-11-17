"""Gera notebook independente e versão Python a partir do material do professor."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
n = json.loads((ROOT / 'material_original/RPA_Lab_original.ipynb').read_text())

def get(i): return ''.join(n['cells'][i]['source'])
def setcell(i, text): n['cells'][i]['source'] = text.splitlines(keepends=True)
def snippet(name): return (ROOT / 'solucao' / name).read_text()
def code(text): return dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=text.splitlines(keepends=True))
def md(text): return dict(cell_type='markdown', metadata={}, source=text.splitlines(keepends=True))

setcell(2, '''# Dependências do laboratório; no terminal use requirements-lock.txt.
import sys, subprocess, importlib.util
pacotes = {'playwright': 'playwright', 'pypdf': 'pypdf', 'fpdf': 'fpdf2',
           'pandas': 'pandas', 'openpyxl': 'openpyxl'}
faltando = [p for m, p in pacotes.items() if importlib.util.find_spec(m) is None]
if faltando:
    subprocess.run([sys.executable, '-m', 'pip', 'install', *faltando], check=True)
subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
from IPython.display import display
print('Ambiente pronto:', sys.version)
''')
setcell(3, get(3).replace('FALHA_ALEATORIA_ERP = 0.20', 'FALHA_ALEATORIA_ERP = 0.0') + '\n# Execução principal controlada; falhas 503 são injetadas nos testes finais.\n')
setcell(5, get(5) + '\n' + snippet('cnpj.py'))
s = get(11).replace(r'([\d./-]{14,18})', r'([A-Za-z0-9./-]{14,18})[ \t]*$')
s = s.replace('if not m:\n            raise', 'if not m and campo == "centro_custo":\n            dados[campo] = ""\n            continue\n        if not m:\n            raise')
s = s.replace(r'([A-Z]+)', r'([^\r\n]*)$')
setcell(11, s)
# Campos opcionais são omitidos na geração para testar ausência real no PDF.
setcell(7, get(7).replace('for rotulo, valor in linhas:\n', 'for rotulo, valor in linhas:\n        if valor is None:\n            continue\n'))
# Separação entre classificação e validação, com definição anterior ao orquestrador.
setcell(13, '# ============================ Validações de negócio ============================\n' + snippet('regras.py') + '\n' + snippet('classificacao.py'))
setcell(15, get(15).replace('TODO seletor', 'Cada seletor').replace('# ERP quer só dígitos', '# CNPJ sem máscara, preservando letras') + '\n' + snippet('interface.py'))
setcell(16, '# Teste isolado incorporado aos testes integrados ao final.\n# Evita criar e apagar uma transação antes do lote principal.\n')
setcell(18, snippet('orquestrador.py'))
setcell(19, '> O teste de repetição está no Desafio 3 e preserva `df_primeiro_lote`. Não reinicie o ERP entre os dois lotes.')
setcell(24, '''# Reconciliação pela interface; banco interno não é fonte operacional do robô.
async def reconciliar():
    async with RoboERP() as robo:
        return await ler_registros_do_erp(robo)
registros_primeiro_lote = rodar(reconciliar())
no_erp = pd.DataFrame(registros_primeiro_lote)
lancadas_robo = df_primeiro_lote[df_primeiro_lote.status == STATUS_SUCESSO]
assert set(lancadas_robo.protocolo) == set(no_erp.protocolo)
conf = lancadas_robo.merge(no_erp[['protocolo', 'valor']], on='protocolo', suffixes=('_pdf', '_erp'))
conf['valor_erp_num'] = conf.valor_erp.str.replace(',', '.').astype(float)
conf['confere'] = (conf.valor_pdf - conf.valor_erp_num).abs() < 0.01
assert conf.confere.all()
assert len(no_erp) == 8
print('Reconciliação aprovada: 8 protocolos e valores conferem pela interface.')
display(conf[['numero', 'protocolo', 'valor_pdf', 'valor_erp', 'confere']])
''')
setcell(26, 'DUPLA = ["PREENCHER NOME COMPLETO 1", "PREENCHER NOME COMPLETO 2"]\nprint("Autores:", DUPLA)\n')
setcell(28, '''# Implementação integrada na Parte 1; regex atualizado na Parte 3.
assert cnpj_valido_v2('12.ABC.345/01DE-35')
assert not cnpj_valido_v2('12.ABC.345/01DE-36')
assert cnpj_valido_v2('23.775.684/0001-07')
for invalido in ['', '00000000000000', '12.ABC.345/01DE-AA', '12.@BC.345/01DE-35']:
    assert not cnpj_valido_v2(invalido)
assert limpar_cnpj_v2('12.abc.345/01de-35') == '12ABC34501DE35'
print('Desafio 1: 8 verificações de CNPJ passaram.')
''')
setcell(29, '''**Reflexão 1:** Uma premissa numérica espalhada por regex, validadores e preenchimento de tela rejeita documentos legítimos ou remove letras silenciosamente. No laboratório isso aparece como exceção de negócio, mas a causa é uma incompatibilidade de software e exige correção do robô. Não há dados aqui para estimar quantos robôs brasileiros são afetados. Monitoraria a taxa de rejeição por campo e a presença de letras nos documentos, preservando evidências. Centralizei a normalização, mantive os casos numéricos e acrescentei testes negativos; validar o DV não comprova existência nem situação cadastral na Receita.''')
setcell(31, snippet('email.py'))
setcell(32, '''**Reflexão 2:** O resumo positivo confirma que o lote foi executado e distingue ausência de pendências de ausência de execução. Em dez segundos, a gerência deve identificar volume, sucessos, exceções e aprovações, com a lista de ações necessárias. O Excel mantém o detalhe auditável. Gerar o arquivo não comprova entrega de e-mail: esta atividade valida o `.eml` e a integridade do anexo, sem SMTP ou envio externo.''')
setcell(34, '''# A implementação está integrada à Parte 5 e ao orquestrador.
antes = rodar(reconciliar())
resultados_reexecucao = rodar(executar_robo())
df_reexecucao = pd.DataFrame([asdict(r) for r in resultados_reexecucao])
depois = rodar(reconciliar())
assert antes == depois
assert (df_reexecucao.status == STATUS_SUCESSO).sum() == 0
assert len(depois) == 8
# Comparação com banco somente como oráculo de teste exigido pelo enunciado.
async def testar_desafio3():
    async with RoboERP() as robo:
        return await ler_notas_do_erp(robo)
lidas = rodar(testar_desafio3())
assert lidas == {(n['numero'], n['cnpj']) for n in ERP_DB['notas']}
df_reexecucao.to_csv(PASTA_SAIDA / 'reexecucao.csv', index=False)
print('Desafio 3: 8 registros antes e depois; zero novos lançamentos.')
''')
setcell(35, '''**Reflexão 3:** O ERP é a fonte de verdade; uma lista em memória desaparece ao reiniciar o robô e pode divergir após uma falha entre gravação e confirmação. Consultar a tela custa navegação e depende do layout, mas recupera o estado efetivamente registrado. O teste executa dois lotes sem apagar o ERP e compara chaves e protocolos. Também consultamos a tela antes de retentar uma gravação incerta. Esta solução pressupõe um único robô; concorrência entre múltiplos trabalhadores ainda exige unicidade transacional no sistema-alvo. O ERP didático está em memória: não oferece persistência após reiniciar o servidor.''')
setcell(37, snippet('testes_interface.py'))
setcell(38, '''**Reflexão 4:** Um mapa centralizado concentra a manutenção dos IDs e permite trocar o layout sem reescrever o preenchimento. Rótulos aproveitam a associação semântica `label/for` e resistem à troca de IDs, mas continuam sujeitos a tradução, mudança do texto ou duplicação de rótulos. Por isso uso correspondência exata e botão identificado por nome, além de esperas pelos desfechos. A comparação medida usa o mesmo ERP e notas distintas para cada variante; a principal vantagem observada é compatibilidade de layout, não uma alegação de maior velocidade.''')
setcell(40, snippet('testes_extra.py'))
setcell(41, '''**Reflexão 5:** A confiança usada aqui é uma proporção de palavras-chave, não uma probabilidade calibrada de acerto. Um termo isolado pode produzir 100% mesmo com descrição ambígua. Registramos descrição, centro atribuído, confiança e versão da regra; empates e baixa confiança não autorizam lançamento. O limiar de 70% é o do exercício e precisaria ser calibrado com dados rotulados reais. A avaliação sintética demonstra os caminhos funcionais, mas não estima desempenho de produção. Um LLM só seria justificável com ganho de qualidade medido, custo por documento, latência e análise de privacidade; ele não foi necessário neste laboratório.''')
setcell(42, '''# Encerramento após todos os testes e artefatos.
SERVIDOR_ERP.shutdown()
SERVIDOR_ERP.server_close()
print('ERP desligado. Artefatos em', PASTA_SAIDA.resolve())
''')
intro = md('''# Entrega — Robô de Contas a Pagar
Solução em Python baseada no notebook do Prof. MSc. Kaio Mesquita. Os enunciados originais foram preservados e as melhorias foram integradas antes do primeiro uso, para permitir **Executar tudo**.

**Como executar:** Python 3.10+, dependências instaladas e Chromium do Playwright. A execução usa modo headless e dados fictícios. O lote principal desativa falhas aleatórias para tornar os resultados verificáveis; os testes finais injetam falhas controladas. Os nomes da dupla devem ser preenchidos na Parte 9.

**Bibliotecas:** Playwright, pypdf, fpdf2, pandas e openpyxl foram mantidas. `email`, `unittest.mock`, `statistics`, `json`, `time` e `unicodedata` pertencem à biblioteca padrão. Jupyter/nbclient servem apenas à execução e registro do notebook.

**Fontes:** [notebook original](https://colab.research.google.com/drive/1NI_HzRBgl6hxqtdb9Yw9XdlkrGIccO6R), [manual oficial de DV da Receita](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf). As reflexões são propostas para revisão e discussão pela dupla.
''')
n['cells'].insert(0, intro)
for indice, c in enumerate(n['cells']):
    c['metadata'] = {}
    if c['cell_type'] == 'code':
        c['execution_count'] = None
        c['outputs'] = []
    c['id'] = f'celula-{indice:03d}'
n['metadata'] = {'kernelspec': {'display_name':'Python 3', 'language':'python', 'name':'python3'}, 'language_info': {'name':'python'}}
(ROOT / 'RPA_Contas_a_Pagar_Resolvido.ipynb').write_text(json.dumps(n, ensure_ascii=False, indent=1))
script = '# Versão Python gerada; fonte: scripts/montar_entrega.py e solucao/*.py\n'
script += '\n\n'.join(''.join(c['source']) for c in n['cells'] if c['cell_type'] == 'code')
(ROOT / 'robo_contas_a_pagar.py').write_text(script)
print('Notebook e script gerados.')
