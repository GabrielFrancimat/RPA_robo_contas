# Versão Python gerada; fonte: scripts/montar_entrega.py e solucao/*.py
# Dependências do laboratório; no terminal use requirements-lock.txt.
import sys, subprocess, importlib.util
pacotes = {'playwright': 'playwright', 'pypdf': 'pypdf', 'fpdf': 'fpdf2',
           'pandas': 'pandas', 'openpyxl': 'openpyxl'}
faltando = [p for m, p in pacotes.items() if importlib.util.find_spec(m) is None]
if faltando:
    subprocess.run([sys.executable, '-m', 'pip', 'install', *faltando], check=True)
subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
from IPython.display import display
print('Ambiente pronto:', sys.version)


# ===================== CONFIGURAÇÃO DO ROBÔ ("Config.xlsx" do REFramework) =====================
from pathlib import Path
import os, sys, re, json, time, random, asyncio, logging, threading, datetime as dt
from dataclasses import dataclass, asdict, field

# Pastas de trabalho — num robô real seriam pastas de rede ou um bucket
BASE           = Path("lab_rpa")
PASTA_ENTRADA  = BASE / "entrada"      # onde chegam os PDFs (caixa de e-mail "baixada")
PASTA_SAIDA    = BASE / "saida"        # relatórios gerados
PASTA_EVID     = BASE / "evidencias"   # prints de tela para auditoria
for p in (PASTA_ENTRADA, PASTA_SAIDA, PASTA_EVID):
    p.mkdir(parents=True, exist_ok=True)

# Sistema-alvo
ERP_HOST, ERP_PORTA = "127.0.0.1", 8765
ERP_URL = f"http://{ERP_HOST}:{ERP_PORTA}"

# ⚠️ Credenciais: NUNCA deixe senha no código em produção.
# Use um cofre (UiPath Orchestrator Assets, CyberArk, Azure Key Vault) ou variáveis de ambiente.
ERP_USUARIO = os.getenv("ERP_USUARIO", "robo.ap")
ERP_SENHA   = os.getenv("ERP_SENHA",   "Rpa@2026")

# Regras de negócio parametrizáveis (mudam sem mexer no código)
LIMITE_APROVACAO   = 50_000.00   # acima disso, a nota vai para aprovação humana
MAX_TENTATIVAS     = 3           # retentativas para exceções de SISTEMA
HEADLESS           = True        # False = você VÊ o robô trabalhando (ótimo para a aula!)
LENTIDAO_MS        = 0           # ex.: 400 para "câmera lenta" quando HEADLESS = False

# Parâmetros do "ERP legado" de laboratório
FALHA_ALEATORIA_ERP = 0.0       # 20% das requisições devolvem "sistema indisponível"
LAYOUT_ERP          = "v1"       # "v2" muda os IDs da tela (usado no Desafio 4)

random.seed(2026)                # reprodutibilidade das NFs geradas

# Log estruturado: tela + arquivo (o log é a "caixa-preta" do robô)
logging.basicConfig(
    level=logging.INFO, force=True,
    format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler(BASE / "robo.log", encoding="utf-8")],
)
log = logging.getLogger("robo-ap")
log.info("Configuração carregada. ERP em %s | limite de aprovação R$ %.2f", ERP_URL, LIMITE_APROVACAO)
# Execução principal controlada; falhas 503 são injetadas nos testes finais.


# ============================ CNPJ: geração e validação ============================
# Regra da Receita: 12 caracteres-base + 2 dígitos verificadores (DV), módulo 11.
PESOS_DV1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
PESOS_DV2 = [6] + PESOS_DV1

def _calcular_dv(base: str, pesos: list[int]) -> str:
    # Cada caractere vale (código ASCII - 48): '0'..'9' → 0..9.
    # (Isso já deixa o terreno pronto para o CNPJ alfanumérico — veja o Desafio 1.)
    soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)

def gerar_cnpj() -> str:
    base = f"{random.randint(10_000_000, 99_999_999)}0001"   # raiz (8) + ordem 0001 = matriz
    dv1 = _calcular_dv(base, PESOS_DV1)
    dv2 = _calcular_dv(base + dv1, PESOS_DV2)
    return formatar_cnpj(base + dv1 + dv2)

def formatar_cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"[^0-9]", "", cnpj)       # ⚠️ só dígitos — premissa que vai quebrar no Desafio 1

def cnpj_valido(cnpj: str) -> bool:
    c = limpar_cnpj(cnpj)
    if len(c) != 14 or c == c[0] * 14:       # "00000000000000" passa no DV, mas é inválido
        return False
    dv1 = _calcular_dv(c[:12], PESOS_DV1)
    dv2 = _calcular_dv(c[:12] + dv1, PESOS_DV2)
    return c[12:] == dv1 + dv2

# Teste rápido — sempre teste suas funções antes de colocá-las num robô!
assert cnpj_valido("23.775.684/0001-07") and not cnpj_valido("23.775.684/0001-08")
print("✔ validação de CNPJ OK")
# Desafio 1: apenas pontuação de apresentação é removida; símbolos inválidos são rejeitados.
def limpar_cnpj_v2(cnpj: str) -> str:
    if not isinstance(cnpj, str):
        return ''
    return re.sub(r'[./\-\s]', '', cnpj).upper()


def cnpj_valido_v2(cnpj: str) -> bool:
    if not isinstance(cnpj, str) or not cnpj.isascii():
        return False
    c = limpar_cnpj_v2(cnpj)
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', c) or len(set(c)) == 1:
        return False
    dv1 = _calcular_dv(c[:12], PESOS_DV1)
    return c[12:] == dv1 + _calcular_dv(c[:12] + dv1, PESOS_DV2)


# Integração: todas as chamadas antigas também recebem o novo comportamento.
limpar_cnpj = limpar_cnpj_v2
cnpj_valido = cnpj_valido_v2


# ============================ Massa de dados: 12 NFs ============================
FORNECEDORES = [
    "Sinaliza Ceará Engenharia LTDA",
    "Asfalto Norte Pavimentação S.A.",
    "LogMov Transportes e Fretes LTDA",
    "Ponte Forte Consultoria em Obras ME",
    "TecVia Sistemas de Monitoramento LTDA",
    "Iracema Manutenção Predial LTDA",
]
CNPJ_FORNECEDOR = {f: gerar_cnpj() for f in FORNECEDORES}

SERVICOS = {
    "OPERACOES":  ["Manutenção preventiva de frota", "Frete de transferência Fortaleza-Recife", "Lavagem técnica de caminhões"],
    "TI":         ["Licença mensal de rastreamento GPS", "Suporte técnico ao sistema de roteirização"],
    "ENGENHARIA": ["Sinalização horizontal do pátio", "Laudo estrutural de galpão", "Recapeamento de acesso interno"],
    "ADMINISTRATIVO": ["Manutenção de ar-condicionado", "Serviço de limpeza e conservação"],
}

def nova_nf(numero: int) -> dict:
    fornecedor = random.choice(FORNECEDORES)
    cc = random.choice(list(SERVICOS))
    return {
        "numero": f"{numero:06d}",
        "data_emissao": (dt.date(2026, 10, 1) + dt.timedelta(days=random.randint(0, 9))).strftime("%d/%m/%Y"),
        "prestador": fornecedor,
        "cnpj": CNPJ_FORNECEDOR[fornecedor],
        "descricao": random.choice(SERVICOS[cc]),
        "valor": round(random.uniform(850, 38_000), 2),
        "centro_custo": cc,
    }

notas_geradas = [nova_nf(4100 + i) for i in range(1, 13)]   # NF 1..12

# --- Pegadinhas (índice = NF - 1) ---
cnpj_ruim = notas_geradas[3]["cnpj"]
notas_geradas[3]["cnpj"] = cnpj_ruim[:-1] + ("0" if cnpj_ruim[-1] != "0" else "1")   # NF 4: DV errado
notas_geradas[6] = dict(notas_geradas[1])                                             # NF 7: duplicada da NF 2
notas_geradas[8]["valor"] = 78_450.90                                                 # NF 9: acima do limite
notas_geradas[10]["valor"] = None                                                     # NF 11: campo ilegível

def brl(v: float) -> str:
    # 12345.6 → "12.345,60" (formato brasileiro)
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

import pandas as pd
pd.DataFrame(notas_geradas).assign(valor=lambda d: d["valor"].map(lambda v: brl(v) if v else "— ilegível —"))

# ============================ Gerar os PDFs ============================
from fpdf import FPDF
# Compatível com fpdf2 (recomendado) e com o antigo "fpdf" 1.7: usamos cell() + ln()
# em vez dos parâmetros new_x/new_y, que só existem no fpdf2.

def _linha(pdf, altura, texto, **kw):
    pdf.cell(0, altura, texto, **kw)
    pdf.ln(altura)                                     # pula para a próxima linha

def gerar_pdf_nf(nf: dict, caminho: Path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    _linha(pdf, 10, "NOTA FISCAL DE SERVIÇOS ELETRÔNICA - NFS-e", align="C")
    pdf.set_font("Helvetica", "", 9)
    _linha(pdf, 6, "Prefeitura Municipal de Fortaleza - Documento fictício para fins didáticos", align="C")
    pdf.ln(6)

    linhas = [
        ("Número da Nota", nf["numero"]),
        ("Data de Emissão", nf["data_emissao"]),
        ("Prestador", nf["prestador"]),
        ("CNPJ do Prestador", nf["cnpj"]),
        ("Tomador", "TransVia Logística LTDA"),
        ("Discriminação do Serviço", nf["descricao"]),
        ("Centro de Custo", nf["centro_custo"]),
    ]
    if nf["valor"] is not None:                        # NF 11 sai sem valor ("scan ruim")
        linhas.append(("Valor Total da Nota", f"R$ {brl(nf['valor'])}"))

    for rotulo, valor in linhas:
        if valor is None:
            continue
        pdf.set_font("Helvetica", "B", 11); pdf.cell(60, 9, f"{rotulo}:")
        pdf.set_font("Helvetica", "", 11);  _linha(pdf, 9, str(valor))
    pdf.output(str(caminho))

# Limpa a "caixa de entrada" e gera os arquivos
for antigo in PASTA_ENTRADA.glob("*.pdf"):
    antigo.unlink()
for i, nf in enumerate(notas_geradas, start=1):
    gerar_pdf_nf(nf, PASTA_ENTRADA / f"NF_{i:02d}_{nf['numero']}.pdf")

print(f"📄 {len(list(PASTA_ENTRADA.glob('*.pdf')))} PDFs em {PASTA_ENTRADA.resolve()}")

# ============================ Mini-ERP legado (NÃO é parte do robô) ============================
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import secrets, html

ERP_DB = {"notas": [], "sessoes": set(), "seq": 0}
CENTROS = ["OPERACOES", "TI", "ENGENHARIA", "ADMINISTRATIVO"]

# IDs dos campos por versão de layout — o v2 simula a "atualização do sistema" que quebra robôs
IDS = {
    "v1": dict(num="txtNumNF", dt="txtDtEmissao", cnpj="txtCNPJ", forn="txtFornecedor",
               desc="txtDescricao", valor="txtValor", cc="cmbCentroCusto", btn="btnGravar", btn_txt="Gravar"),
    "v2": dict(num="nfNumero", dt="nfData", cnpj="inputCnpjFornecedor", forn="nfRazaoSocial",
               desc="nfServico", valor="nfValorTotal", cc="selectCC", btn="btnSalvarLancamento", btn_txt="Salvar lançamento"),
}

CSS = ("<style>body{font-family:Tahoma,Verdana,sans-serif;background:#d4d0c8;margin:0}"
       ".top{background:#0a246a;color:#fff;padding:6px 12px;font-weight:bold}"
       ".box{background:#ece9d8;border:2px outset #fff;margin:24px auto;padding:16px;width:560px}"
       "label{display:inline-block;width:170px;font-size:13px}input,select{margin:4px 0;width:340px}"
       ".err{color:#b00;font-weight:bold}.ok{color:#060;font-weight:bold}table{border-collapse:collapse;font-size:12px}"
       "td,th{border:1px solid #888;padding:3px 6px}</style>")

def pagina(titulo, corpo):
    return f"<html><head><meta charset='utf-8'><title>{titulo}</title>{CSS}</head><body>" \
           f"<div class='top'>SIGA-ERP 4.2 &middot; TransVia Logística &middot; {titulo}</div>" \
           f"<div class='box'>{corpo}</div></body></html>"

class ERPHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):          # silencia o log padrão do http.server
        pass

    # ---------- utilitários ----------
    def _responder(self, corpo, status=200, headers=None):
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _redirecionar(self, destino, headers=None):
        self.send_response(303)
        self.send_header("Location", destino)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _logado(self):
        cookie = self.headers.get("Cookie", "")
        m = re.search(r"SESSAO=([a-f0-9]+)", cookie)
        return bool(m and m.group(1) in ERP_DB["sessoes"])

    def _form(self):
        tam = int(self.headers.get("Content-Length", 0))
        return {k: v[0].strip() for k, v in parse_qs(self.rfile.read(tam).decode("utf-8")).items()}

    # ---------- GET ----------
    def do_GET(self):
        time.sleep(random.uniform(0.05, 0.35))            # sistema lento
        rota = urlparse(self.path).path
        if rota in ("/", "/login"):
            return self._responder(pagina("Login", """
              <h3>Acesso ao sistema</h3><form method='post' action='/login'>
              <label for='usuario'>Usuário</label><input id='usuario' name='usuario'><br>
              <label for='senha'>Senha</label><input id='senha' name='senha' type='password'><br>
              <button id='btnEntrar' type='submit'>Entrar</button></form>"""))
        if not self._logado():
            return self._redirecionar("/login")
        if rota == "/home":
            return self._responder(pagina("Início", """<p class='ok' id='boasVindas'>Bem-vindo(a)!</p>
              <a id='lnkNovaNota' href='/nova-nota'>Lançar nota fiscal</a> | <a href='/notas'>Notas lançadas</a>"""))
        if rota == "/nova-nota":
            i = IDS[LAYOUT_ERP]
            opcoes = "".join(f"<option value='{c}'>{c.title()}</option>" for c in CENTROS)
            return self._responder(pagina("Lançamento de NF", f"""
              <h3>Lançamento de Nota Fiscal de Serviço</h3><form method='post' action='/nova-nota'>
              <label for='{i['num']}'>Nº da NF</label><input id='{i['num']}' name='numero'><br>
              <label for='{i['dt']}'>Emissão (dd/mm/aaaa)</label><input id='{i['dt']}' name='data_emissao'><br>
              <label for='{i['cnpj']}'>CNPJ fornecedor</label><input id='{i['cnpj']}' name='cnpj'><br>
              <label for='{i['forn']}'>Razão social</label><input id='{i['forn']}' name='fornecedor'><br>
              <label for='{i['desc']}'>Descrição</label><input id='{i['desc']}' name='descricao'><br>
              <label for='{i['valor']}'>Valor (ex.: 1234,56)</label><input id='{i['valor']}' name='valor'><br>
              <label for='{i['cc']}'>Centro de custo</label><select id='{i['cc']}' name='centro_custo'>
                 <option value=''>-- selecione --</option>{opcoes}</select><br>
              <button id='{i['btn']}' type='submit'>{i['btn_txt']}</button></form>"""))
        if rota == "/notas":
            linhas = "".join(
                f"<tr><td>{n['protocolo']}</td><td>{n['numero']}</td><td>{n['cnpj']}</td>"
                f"<td>{html.escape(n['fornecedor'])}</td><td>{n['valor']}</td><td>{n['centro_custo']}</td></tr>"
                for n in ERP_DB["notas"])
            return self._responder(pagina("Notas lançadas", f"""<table id='tblNotas'>
              <tr><th>Protocolo</th><th>NF</th><th>CNPJ</th><th>Fornecedor</th><th>Valor</th><th>CC</th></tr>{linhas}</table>"""))
        self._responder(pagina("Erro", "<p class='err'>Página não encontrada</p>"), 404)

    # ---------- POST ----------
    def do_POST(self):
        time.sleep(random.uniform(0.1, 0.6))
        rota = urlparse(self.path).path
        if rota == "/login":
            f = self._form()
            if f.get("usuario") == ERP_USUARIO and f.get("senha") == ERP_SENHA:
                token = secrets.token_hex(8)
                ERP_DB["sessoes"].add(token)
                return self._redirecionar("/home", {"Set-Cookie": f"SESSAO={token}; Path=/"})
            return self._responder(pagina("Login", "<p class='err' id='erroLogin'>Usuário ou senha inválidos</p>"
                                          "<a href='/login'>Voltar</a>"), 401)
        if not self._logado():
            return self._redirecionar("/login")
        if rota == "/nova-nota":
            if random.random() < FALHA_ALEATORIA_ERP:          # instabilidade do legado
                return self._responder(pagina("Erro", "<p class='err' id='erroSistema'>"
                                              "Serviço temporariamente indisponível (ORA-12541). Tente novamente.</p>"), 503)
            f = self._form()
            obrig = ["numero", "data_emissao", "cnpj", "fornecedor", "descricao", "valor", "centro_custo"]
            faltando = [c for c in obrig if not f.get(c)]
            erro = None
            if faltando:
                erro = f"Campos obrigatórios não preenchidos: {', '.join(faltando)}"
            elif not re.fullmatch(r"\d{2}/\d{2}/\d{4}", f["data_emissao"]):
                erro = "Data inválida. Use dd/mm/aaaa."
            elif not re.fullmatch(r"\d+(,\d{2})?", f["valor"]):
                erro = "Valor inválido. Use apenas números e vírgula (ex.: 1234,56)."
            elif any(n["numero"] == f["numero"] and n["cnpj"] == f["cnpj"] for n in ERP_DB["notas"]):
                erro = "Nota já lançada para este fornecedor."
            if erro:
                return self._responder(pagina("Erro", f"<p class='err' id='erroValidacao'>{erro}</p>"), 422)
            ERP_DB["seq"] += 1
            protocolo = f"AP-2026-{ERP_DB['seq']:05d}"
            ERP_DB["notas"].append({**f, "protocolo": protocolo, "lancado_em": dt.datetime.now().isoformat()})
            return self._responder(pagina("Sucesso", f"<p class='ok'>Nota gravada com sucesso.</p>"
                                          f"<p>Protocolo: <b id='protocolo'>{protocolo}</b></p>"
                                          "<a href='/nova-nota'>Nova nota</a>"))
        self._responder(pagina("Erro", "<p class='err'>Rota inválida</p>"), 404)

def iniciar_erp():
    global SERVIDOR_ERP
    try:                                      # se a célula for rodada de novo, derruba o anterior
        SERVIDOR_ERP.shutdown(); SERVIDOR_ERP.server_close()
    except NameError:
        pass
    ThreadingHTTPServer.allow_reuse_address = True
    SERVIDOR_ERP = ThreadingHTTPServer((ERP_HOST, ERP_PORTA), ERPHandler)
    threading.Thread(target=SERVIDOR_ERP.serve_forever, daemon=True).start()
    log.info("🖥️  ERP legado no ar em %s  (layout %s)", ERP_URL, LAYOUT_ERP)

ERP_DB.update(notas=[], sessoes=set(), seq=0)   # base limpa a cada execução
iniciar_erp()

# ============================ Exceções e modelo de dados ============================
from pypdf import PdfReader

class ErroNegocio(Exception):
    '''Dado inválido ou regra violada. Retentar NÃO resolve → humano analisa.'''

class ErroSistema(Exception):
    '''Falha técnica/transitória (timeout, 503, elemento não carregou). Retentar PODE resolver.'''

@dataclass
class NotaFiscal:
    arquivo: str
    numero: str
    data_emissao: str
    prestador: str
    cnpj: str
    descricao: str
    centro_custo: str
    valor: float

# Um padrão por campo. (?m) = multilinha; [ \t]* evita "pular" para a linha de baixo
PADROES = {
    "numero":       r"(?m)^N[úu]mero da Nota:[ \t]*(\d+)",
    "data_emissao": r"(?m)^Data de Emiss[ãa]o:[ \t]*(\d{2}/\d{2}/\d{4})",
    "prestador":    r"(?m)^Prestador:[ \t]*(.+)$",
    "cnpj":         r"(?m)^CNPJ do Prestador:[ \t]*([A-Za-z0-9./-]{14,18})[ \t]*$",
    "descricao":    r"(?m)^Discrimina[çc][ãa]o do Servi[çc]o:[ \t]*(.+)$",
    "centro_custo": r"(?m)^Centro de Custo:[ \t]*([^\r\n]*)$",
    "valor":        r"(?m)^Valor Total da Nota:[ \t]*R\$[ \t]*([\d.]+,\d{2})",
}

def brl_para_float(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))   # "12.345,67" → 12345.67

def extrair_nota(caminho: Path) -> NotaFiscal:
    try:
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(caminho).pages)
    except Exception as e:                                    # arquivo corrompido
        raise ErroNegocio(f"PDF ilegível: {e}") from e
    # O extrator do PDF devolve "Rótulo: valor" colado; normalizamos espaços
    texto = re.sub(r"[ \t]+", " ", texto)
    dados = {}
    for campo, padrao in PADROES.items():
        m = re.search(padrao, texto)
        if not m and campo == "centro_custo":
            dados[campo] = ""
            continue
        if not m:
            raise ErroNegocio(f"Campo '{campo}' não encontrado no documento")
        dados[campo] = m.group(1).strip()
    dados["valor"] = brl_para_float(dados["valor"])
    return NotaFiscal(arquivo=caminho.name, **dados)

# Teste com o primeiro PDF — e veja o texto "cru" que o robô enxerga
primeiro = sorted(PASTA_ENTRADA.glob("*.pdf"))[0]
print(PdfReader(primeiro).pages[0].extract_text()[:400], "\n...\n")
extrair_nota(primeiro)

# ============================ Validações de negócio ============================
# Validações de negócio: validar antes de reservar uma chave no lote.
import math

STATUS_SUCESSO = 'SUCESSO'
STATUS_NEGOCIO = 'EXCECAO_NEGOCIO'
STATUS_SISTEMA = 'EXCECAO_SISTEMA'
STATUS_APROVACAO = 'PENDENTE_APROVACAO'


def validar_nota(nota: NotaFiscal, chaves_ja_vistas: set) -> str | None:
    if not isinstance(nota.numero, str) or not re.fullmatch(r'[0-9]+', nota.numero):
        raise ErroNegocio('Número de nota ausente ou inválido')
    for nome in ['prestador', 'descricao']:
        valor = getattr(nota, nome)
        if not isinstance(valor, str) or not valor.strip():
            raise ErroNegocio(f'Campo obrigatório vazio: {nome}')
    try:
        if not re.fullmatch(r'[0-9]{2}/[0-9]{2}/[0-9]{4}', nota.data_emissao):
            raise ValueError('Formato de data inválido')
        dt.datetime.strptime(nota.data_emissao, '%d/%m/%Y')
    except (TypeError, ValueError):
        raise ErroNegocio('Data de emissão inválida: informe uma data real em dd/mm/aaaa')
    if not cnpj_valido(nota.cnpj):
        raise ErroNegocio(f'CNPJ inválido: {nota.cnpj}')
    if isinstance(nota.valor, bool) or not isinstance(nota.valor, (int, float)) or not math.isfinite(nota.valor) or nota.valor <= 0:
        raise ErroNegocio('Valor deve ser um número finito e positivo')
    if nota.centro_custo and nota.centro_custo not in CENTROS:
        raise ErroNegocio(f'Centro de custo inválido: {nota.centro_custo}')
    chave = (nota.numero, limpar_cnpj(nota.cnpj))
    if chave in chaves_ja_vistas:
        raise ErroNegocio(f'NF {nota.numero} duplicada para o CNPJ {nota.cnpj}')
    chaves_ja_vistas.add(chave)
    return STATUS_APROVACAO if nota.valor > LIMITE_APROVACAO else None

import unicodedata
import re

PALAVRAS_CHAVE = {
    'OPERACOES': ['frota', 'frete', 'caminh'],
    'TI': ['licença', 'sistema', 'software', 'gps'],
    'ENGENHARIA': ['sinalização', 'laudo', 'recapeamento', 'estrutural'],
    'ADMINISTRATIVO': ['limpeza', 'ar-condicionado', 'conservação'],
}
LIMIAR_CONFIANCA = 0.7
VERSAO_CLASSIFICADOR = 'palavras-chave-1.1'


def normalizar_texto(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto.casefold())
                   if unicodedata.category(c) != 'Mn')


def classificar_centro_custo(descricao: str) -> tuple[str | None, float]:
    texto = normalizar_texto(descricao)
    def corresponde(palavra):
        raiz = re.escape(normalizar_texto(palavra))
        padrao = rf'\b{raiz}\w*\b' if palavra == 'caminh' else rf'\b{raiz}\b'
        return bool(re.search(padrao, texto))
    pontos = {cc: sum(corresponde(p) for p in palavras)
              for cc, palavras in PALAVRAS_CHAVE.items()}
    total = sum(pontos.values())
    if not total:
        return None, 0.0
    maior = max(pontos.values())
    vencedores = [cc for cc, n in pontos.items() if n == maior]
    confianca = maior / total
    # Empate nunca escolhe um centro arbitrariamente.
    return (vencedores[0] if len(vencedores) == 1 else None), confianca


# ============================ Camada de UI ============================
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

def rodar(corrotina):
    '''Executa uma função async do robô num event loop próprio, em outra thread.
    Resolve o NotImplementedError do Playwright no Jupyter do Windows.'''
    saida = {}
    def alvo():
        loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            saida["valor"] = loop.run_until_complete(corrotina)
        except BaseException as e:
            saida["erro"] = e
        finally:
            loop.close()
    t = threading.Thread(target=alvo)
    t.start(); t.join()
    if "erro" in saida:
        raise saida["erro"]
    return saida.get("valor")

# Object Repository: Cada seletor mora aqui. Mudou a tela? Muda só este dicionário.
SELETORES = {
    "login_usuario": "#usuario",
    "login_senha":   "#senha",
    "login_botao":   "#btnEntrar",
    "home_ok":       "#boasVindas",
    "nf_numero":     "#txtNumNF",
    "nf_data":       "#txtDtEmissao",
    "nf_cnpj":       "#txtCNPJ",
    "nf_fornecedor": "#txtFornecedor",
    "nf_descricao":  "#txtDescricao",
    "nf_valor":      "#txtValor",
    "nf_cc":         "#cmbCentroCusto",
    "nf_gravar":     "#btnGravar",
    "res_protocolo": "#protocolo",
    "res_erro_val":  "#erroValidacao",
    "res_erro_sis":  "#erroSistema",
}

class RoboERP:
    '''Encapsula o navegador. Uso: async with RoboERP() as robo: await robo.lancar(nota)'''

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=HEADLESS, slow_mo=LENTIDAO_MS)
        self.page = await (await self.browser.new_context(locale="pt-BR")).new_page()
        self.page.set_default_timeout(8_000)          # nada de esperar "para sempre"
        await self.login()
        return self

    async def __aexit__(self, *exc):
        await self.browser.close()
        await self._pw.stop()

    async def login(self):
        p, s = self.page, SELETORES
        await p.goto(f"{ERP_URL}/login")
        await p.fill(s["login_usuario"], ERP_USUARIO)
        await p.fill(s["login_senha"], ERP_SENHA)
        await p.click(s["login_botao"])
        try:
            await p.wait_for_selector(s["home_ok"])
        except PWTimeout:
            # Senha errada não se resolve com retentativa → é de negócio (ou de configuração)
            raise ErroNegocio("Falha de login no ERP — verifique as credenciais do robô")
        log.info("🔐 Login realizado como %s", ERP_USUARIO)

    async def evidencia(self, nome: str) -> str:
        caminho = PASTA_EVID / f"{dt.datetime.now():%H%M%S}_{nome}.png"
        await self.page.screenshot(path=str(caminho), full_page=True)
        return str(caminho)

    async def lancar(self, nota: NotaFiscal) -> str:
        '''Preenche o formulário e devolve o protocolo do ERP.'''
        p, s = self.page, SELETORES
        await p.goto(f"{ERP_URL}/nova-nota")
        if "/login" in p.url:                          # sessão expirou? loga de novo
            await self.login(); await p.goto(f"{ERP_URL}/nova-nota")
        try:
            await p.wait_for_selector(s["nf_numero"])
        except PWTimeout:
            raise ErroSistema("Tela de lançamento não carregou (seletor não encontrado)")

        # TRANSFORMAÇÃO para o formato que o ERP aceita
        await p.fill(s["nf_numero"], nota.numero)
        await p.fill(s["nf_data"], nota.data_emissao)
        await p.fill(s["nf_cnpj"], limpar_cnpj(nota.cnpj))           # CNPJ sem máscara, preservando letras
        await p.fill(s["nf_fornecedor"], nota.prestador)
        await p.fill(s["nf_descricao"], nota.descricao)
        await p.fill(s["nf_valor"], f"{nota.valor:.2f}".replace(".", ","))   # 1234.5 → "1234,50"
        await p.select_option(s["nf_cc"], nota.centro_custo)
        await p.click(s["nf_gravar"])

        # Espera por QUALQUER um dos três desfechos possíveis
        desfecho = await p.wait_for_selector(
            f'{s["res_protocolo"]}, {s["res_erro_val"]}, {s["res_erro_sis"]}')
        id_el = await desfecho.get_attribute("id")
        texto = (await desfecho.inner_text()).strip()
        if id_el == s["res_protocolo"].lstrip("#"):
            return texto
        if id_el == s["res_erro_sis"].lstrip("#"):
            raise ErroSistema(texto)
        raise ErroNegocio(f"ERP recusou: {texto}")

print("Camada de UI pronta. Seletores mapeados:", len(SELETORES))
from functools import wraps
from playwright.async_api import Error as PWError


def erro_de_navegador_como_sistema(funcao):
    @wraps(funcao)
    async def executar(*args, **kwargs):
        try:
            return await funcao(*args, **kwargs)
        except PWError as erro:
            # Uma navegação abortada pode ainda estar transitando para a página
            # de erro do Chromium. Isola a retentativa numa nova aba, preservando cookies.
            if 'net::ERR_' in str(erro) or 'interrupted by another navigation' in str(erro):
                robo = args[0]
                anterior = robo.page
                robo.page = await anterior.context.new_page()
                robo.page.set_default_timeout(8000)
                await anterior.close()
            raise ErroSistema(f'Falha de navegador: {erro}') from erro
    return executar


async def iniciar_robo_com_limpeza(self):
    self._pw = await async_playwright().start()
    try:
        self.browser = await self._pw.chromium.launch(headless=HEADLESS, slow_mo=LENTIDAO_MS)
        self.page = await (await self.browser.new_context(locale='pt-BR')).new_page()
        self.page.set_default_timeout(8000)
        await self.login()
        return self
    except BaseException:
        try:
            if hasattr(self, 'browser'):
                await self.browser.close()
        finally:
            await self._pw.stop()
        raise


RoboERP.__aenter__ = iniciar_robo_com_limpeza

# Desafios 3 e 4. A consulta operacional usa exclusivamente a interface.
SELETORES_V1 = dict(SELETORES)
SELETORES_V2 = dict(SELETORES, nf_numero='#nfNumero', nf_data='#nfData',
    nf_cnpj='#inputCnpjFornecedor', nf_fornecedor='#nfRazaoSocial',
    nf_descricao='#nfServico', nf_valor='#nfValorTotal', nf_cc='#selectCC',
    nf_gravar='#btnSalvarLancamento')


@erro_de_navegador_como_sistema
async def ler_registros_do_erp(robo) -> list[dict]:
    p = robo.page
    resposta = await p.goto(f'{ERP_URL}/notas')
    if '/login' in p.url:
        await robo.login()
        resposta = await p.goto(f'{ERP_URL}/notas')
    if resposta and resposta.status >= 500:
        raise ErroSistema(f'Consulta ao ERP: HTTP {resposta.status}')
    await p.locator('#tblNotas').wait_for()
    cabecalho = [t.strip() for t in await p.locator('#tblNotas tr').first.locator('th').all_inner_texts()]
    if cabecalho != ['Protocolo', 'NF', 'CNPJ', 'Fornecedor', 'Valor', 'CC']:
        raise ErroSistema(f'Cabeçalho inesperado na tabela do ERP: {cabecalho}')
    registros = []
    for linha in await p.locator('#tblNotas tr').all():
        valores = await linha.locator('td').all_inner_texts()
        if not valores:  # cabeçalho
            continue
        if len(valores) != 6:
            raise ErroSistema('Estrutura da tabela de notas mudou')
        protocolo, numero, cnpj, fornecedor, valor, centro = valores
        registros.append(dict(protocolo=protocolo.strip(), numero=numero.strip(),
            cnpj=limpar_cnpj(cnpj), fornecedor=fornecedor, valor=valor, centro_custo=centro))
    return registros


async def ler_notas_do_erp(robo) -> set:
    return {(n['numero'], n['cnpj']) for n in await ler_registros_do_erp(robo)}


@erro_de_navegador_como_sistema
async def lancar_por_rotulo(robo, nota) -> str:
    p = robo.page
    await p.goto(f'{ERP_URL}/nova-nota')
    if '/login' in p.url:
        await robo.login()
        await p.goto(f'{ERP_URL}/nova-nota')
    campos = {'Nº da NF': nota.numero, 'CNPJ fornecedor': limpar_cnpj(nota.cnpj),
        'Emissão (dd/mm/aaaa)': nota.data_emissao, 'Razão social': nota.prestador,
        'Descrição': nota.descricao, 'Valor (ex.: 1234,56)': f'{nota.valor:.2f}'.replace('.', ',')}
    for rotulo, valor in campos.items():
        await p.get_by_label(rotulo, exact=True).fill(valor)
    await p.get_by_label('Centro de custo', exact=True).select_option(nota.centro_custo)
    await p.get_by_role('button', name=re.compile(r'^(Gravar|Salvar lançamento)$')).click()
    desfecho = await p.wait_for_selector('#protocolo, #erroValidacao, #erroSistema')
    identificador = await desfecho.get_attribute('id')
    mensagem = (await desfecho.inner_text()).strip()
    if identificador == 'protocolo':
        return mensagem
    if identificador == 'erroSistema':
        raise ErroSistema(mensagem)
    raise ErroNegocio(f'ERP recusou: {mensagem}')


# Preserva a implementação por IDs para demonstrar as duas partes do desafio 4.
RoboERP.lancar_por_id = erro_de_navegador_como_sistema(RoboERP.lancar)
RoboERP.lancar = lancar_por_rotulo


# Teste isolado incorporado aos testes integrados ao final.
# Evita criar e apagar uma transação antes do lote principal.


@dataclass
class Resultado:
    arquivo: str
    status: str
    numero: str = ''
    fornecedor: str = ''
    cnpj: str = ''
    valor: float | None = None
    protocolo: str = ''
    tentativas: int = 0
    mensagem: str = ''
    evidencia: str = ''
    duracao_s: float = 0.0
    centro_custo: str = ''
    confianca: float | None = None
    classificador: str = ''
    descricao: str = ''


async def com_retentativas(funcao, *args, tentativas=MAX_TENTATIVAS, espera_base=0.5):
    for n in range(1, tentativas + 1):
        try:
            return await funcao(*args), n
        except (ErroSistema, PWTimeout) as e:
            if n == tentativas:
                erro = ErroSistema(f'Falhou após {n} tentativas: {e}')
                erro.tentativas = n
                raise erro from e
            log.warning('Retentativa %d/%d: %s', n, tentativas, e)
            await asyncio.sleep(espera_base * 2 ** (n - 1))


async def executar_robo() -> list[Resultado]:
    inicio = time.perf_counter()
    resultados = []
    chaves_vistas = set()
    async with RoboERP() as robo:
        ja_no_erp, _ = await com_retentativas(ler_notas_do_erp, robo)
        for item in sorted(PASTA_ENTRADA.glob('*.pdf')):
            t0 = time.perf_counter()
            r = Resultado(arquivo=item.name, status='')
            try:
                nota = extrair_nota(item)
                r.numero, r.fornecedor, r.cnpj, r.valor = nota.numero, nota.prestador, nota.cnpj, nota.valor
                r.descricao = nota.descricao
                chave = (nota.numero, limpar_cnpj(nota.cnpj))
                if chave in ja_no_erp:
                    raise ErroNegocio('Já existe no ERP — ignorado por idempotência')
                decisao = validar_nota(nota, chaves_vistas)
                motivos = []
                if decisao == STATUS_APROVACAO:
                    motivos.append(f'Valor acima do limite de R$ {brl(LIMITE_APROVACAO)}')
                if not nota.centro_custo:
                    centro, r.confianca = classificar_centro_custo(nota.descricao)
                    r.classificador = VERSAO_CLASSIFICADOR
                    if centro is None or r.confianca < LIMIAR_CONFIANCA:
                        motivos.append(f'Centro de custo incerto: confiança {r.confianca:.0%}')
                    else:
                        nota.centro_custo = centro
                elif nota.centro_custo not in CENTROS:
                    raise ErroNegocio(f'Centro de custo inválido: {nota.centro_custo}')
                r.centro_custo = nota.centro_custo
                if motivos:
                    r.status, r.mensagem = STATUS_APROVACAO, '; '.join(motivos)
                else:
                    # Antes de repetir um POST com resposta incerta, consulta o ERP.
                    # Evita duplicação se a gravação ocorreu e apenas a resposta se perdeu.
                    async def transacao():
                        r.tentativas += 1
                        if r.tentativas > 1:
                            for registro in await ler_registros_do_erp(robo):
                                if (registro['numero'], registro['cnpj']) == chave:
                                    return registro['protocolo']
                        return await robo.lancar(nota)
                    r.protocolo, _ = await com_retentativas(transacao)
                    r.status = STATUS_SUCESSO
                    ja_no_erp.add(chave)
            except ErroNegocio as e:
                r.status, r.mensagem = STATUS_NEGOCIO, str(e)
            except Exception as e:
                r.status, r.mensagem = STATUS_SISTEMA, str(e)
                # A falha da captura não pode encerrar o lote.
                try:
                    r.evidencia = await robo.evidencia(item.stem)
                except Exception as captura:
                    log.warning('Não foi possível capturar evidência: %s', captura)
            r.duracao_s = round(time.perf_counter() - t0, 4)
            log.info('%s | %s | %s', item.name, r.status, r.protocolo or r.mensagem)
            resultados.append(r)
    log.info('Lote concluído em %.2fs', time.perf_counter() - inicio)
    return resultados


resultados = rodar(executar_robo())
df = pd.DataFrame([asdict(r) for r in resultados])
df_primeiro_lote = df.copy(deep=True)
display(df[['arquivo', 'status', 'numero', 'valor', 'protocolo', 'tentativas', 'mensagem']])


# ============================ Relatório Excel ============================
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Premissas de ROI — DISCUTA com a turma se são realistas!
MIN_HUMANO_POR_NOTA = 4.0        # minutos que o analista gasta por nota
NOTAS_POR_MES       = 800
CUSTO_HORA_ANALISTA = 45.00      # R$/h com encargos (hipotético)
CUSTO_MENSAL_ROBO   = 1_500.00   # R$/mês: infraestrutura + manutenção (hipotético)

total = len(df)
ok = (df.status == STATUS_SUCESSO).sum()
taxa_auto = ok / total
seg_robo = df.loc[df.status == STATUS_SUCESSO, "duracao_s"].mean()
horas_economizadas = NOTAS_POR_MES * taxa_auto * MIN_HUMANO_POR_NOTA / 60
economia_mes = horas_economizadas * CUSTO_HORA_ANALISTA - CUSTO_MENSAL_ROBO

resumo = pd.DataFrame({
    "Indicador": ["Notas processadas", "Lançadas pelo robô", "Taxa de automação (STP)",
                  "Exceções de negócio", "Exceções de sistema", "Aguardando aprovação",
                  "Tempo médio do robô por nota (s)", "Tempo humano por nota (s)",
                  "Horas liberadas por mês (projeção)", "Economia líquida mensal (R$, projeção)"],
    "Valor": [total, ok, f"{taxa_auto:.0%}",
              (df.status == STATUS_NEGOCIO).sum(), (df.status == STATUS_SISTEMA).sum(),
              (df.status == STATUS_APROVACAO).sum(),
              round(seg_robo, 1), MIN_HUMANO_POR_NOTA * 60,
              round(horas_economizadas, 1), f"R$ {brl(economia_mes)}"],
})

arquivo_rel = PASTA_SAIDA / f"relatorio_robo_AP_{dt.datetime.now():%Y%m%d_%H%M}.xlsx"
with pd.ExcelWriter(arquivo_rel, engine="openpyxl") as xw:
    resumo.to_excel(xw, sheet_name="Resumo", index=False)
    df[df.status == STATUS_SUCESSO].to_excel(xw, sheet_name="Lançadas", index=False)
    df[df.status != STATUS_SUCESSO].to_excel(xw, sheet_name="Para analisar", index=False)
    for ws in xw.book.worksheets:                         # formatação: cabeçalho + largura
        for cel in ws[1]:
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = PatternFill("solid", fgColor="1E4D45")
            cel.alignment = Alignment(horizontal="center")
        for col in ws.columns:
            largura = max(len(str(c.value or "")) for c in col) + 2
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(largura, 60)
        ws.freeze_panes = "A2"

print("📊 Relatório salvo em", arquivo_rel.resolve())
resumo

# Reconciliação pela interface; banco interno não é fonte operacional do robô.
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


DUPLA = ["PREENCHER NOME COMPLETO 1", "PREENCHER NOME COMPLETO 2"]
print("Autores:", DUPLA)


# Implementação integrada na Parte 1; regex atualizado na Parte 3.
assert cnpj_valido_v2('12.ABC.345/01DE-35')
assert not cnpj_valido_v2('12.ABC.345/01DE-36')
assert cnpj_valido_v2('23.775.684/0001-07')
for invalido in ['', '00000000000000', '12.ABC.345/01DE-AA', '12.@BC.345/01DE-35']:
    assert not cnpj_valido_v2(invalido)
assert limpar_cnpj_v2('12.abc.345/01de-35') == '12ABC34501DE35'
print('Desafio 1: 8 verificações de CNPJ passaram.')


from email.message import EmailMessage
from email import policy
from email.parser import BytesParser


def gerar_email(df, arquivo_excel) -> Path:
    msg = EmailMessage()
    msg['From'] = 'robo.ap@transvia.com.br'
    msg['To'] = 'gerencia.ap@transvia.com.br'
    msg['Subject'] = f'Contas a pagar | {dt.date.today():%d/%m/%Y} | {len(df)} notas'
    resumo_status = df.status.value_counts().to_dict()
    linhas = ['Resumo do processamento de contas a pagar:', '']
    for status in [STATUS_SUCESSO, STATUS_NEGOCIO, STATUS_SISTEMA, STATUS_APROVACAO]:
        linhas.append(f'{status}: {resumo_status.get(status, 0)}')
    linhas.extend(['', 'Notas para análise humana:'])
    pendentes = df[df.status != STATUS_SUCESSO]
    if pendentes.empty:
        linhas.append('Nenhuma pendência.')
    for r in pendentes.itertuples():
        linhas.append(f'- {r.arquivo} | NF {r.numero or "não extraída"} | {r.status} | {r.mensagem}')
    msg.set_content('\n'.join(linhas))
    arquivo_excel = Path(arquivo_excel)
    msg.add_attachment(arquivo_excel.read_bytes(), maintype='application',
        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=arquivo_excel.name)
    caminho = PASTA_SAIDA / 'resumo_lote.eml'
    caminho.write_bytes(msg.as_bytes(policy=policy.SMTP))
    return caminho


arquivo_email = gerar_email(df_primeiro_lote, arquivo_rel)
email_lido = BytesParser(policy=policy.default).parsebytes(arquivo_email.read_bytes())
anexos = list(email_lido.iter_attachments())
assert len(anexos) == 1 and anexos[0].get_payload(decode=True) == arquivo_rel.read_bytes()
assert str(len(df_primeiro_lote)) in str(email_lido['Subject'])
print('E-mail validado (incluindo integridade do anexo):', arquivo_email)


# A implementação está integrada à Parte 5 e ao orquestrador.
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


from dataclasses import replace
from unittest.mock import patch
import statistics

async def validar_interface():
    global LAYOUT_ERP, SELETORES
    layout_anterior, seletores_anteriores = LAYOUT_ERP, SELETORES
    nota_base = extrair_nota(sorted(PASTA_ENTRADA.glob('*.pdf'))[0])
    medidas = []
    try:
        async with RoboERP() as robo:
            # Mudança de IDs: falha esperada e documentada; timeout curto só neste teste.
            LAYOUT_ERP, SELETORES = 'v2', SELETORES_V1
            robo.page.set_default_timeout(700)
            try:
                await robo.lancar_por_id(replace(nota_base, numero='800000'))
                raise AssertionError('O seletor antigo deveria falhar no layout v2')
            except ErroSistema:
                print('Falha esperada: mapa v1 não encontra campo no layout v2.')
                await robo.evidencia('layout_v2_seletor_antigo')
            finally:
                robo.page.set_default_timeout(8000)
            # Intercala IDs/rótulos em cada layout para reduzir viés de ordem.
            for layout in ['v1', 'v2']:
                LAYOUT_ERP = layout
                SELETORES = SELETORES_V1 if layout == 'v1' else SELETORES_V2
                for repeticao in range(3):
                    for estrategia in ['ids', 'rotulos']:
                        numero = str(810000 + len(medidas))
                        nota = replace(nota_base, numero=numero)
                        inicio = time.perf_counter()
                        funcao = robo.lancar_por_id if estrategia == 'ids' else robo.lancar
                        protocolo = await funcao(nota)
                        medidas.append(dict(layout=layout, estrategia=estrategia,
                            repeticao=repeticao + 1, segundos=time.perf_counter() - inicio,
                            protocolo=protocolo))
                await robo.evidencia(f'layout_{layout}_sucesso')
            # 503 real no navegador, injetado antes de enviar a primeira gravação.
            chamadas = {'post': 0}
            async def falhar_uma_vez(route):
                if route.request.method == 'POST':
                    chamadas['post'] += 1
                    if chamadas['post'] == 1:
                        await route.fulfill(status=503, content_type='text/html',
                            body='<p id="erroSistema">Indisponibilidade controlada</p>')
                        return
                await route.continue_()
            await robo.page.route('**/nova-nota', falhar_uma_vez)
            try:
                protocolo, tentativas = await com_retentativas(robo.lancar,
                    replace(nota_base, numero='820001'), espera_base=0.01)
                assert tentativas == 2 and chamadas['post'] == 2
            finally:
                await robo.page.unroute('**/nova-nota', falhar_uma_vez)
            # Erro de negócio não deve receber retentativas.
            contador = 0
            async def negocio():
                nonlocal contador
                contador += 1
                raise ErroNegocio('Documento inválido')
            try:
                await com_retentativas(negocio, espera_base=0)
            except ErroNegocio:
                pass
            assert contador == 1
            # Esgotamento de erro de sistema registra o número de tentativas.
            contador_sistema = 0
            async def sistema():
                nonlocal contador_sistema
                contador_sistema += 1
                raise ErroSistema('Falha persistente')
            try:
                await com_retentativas(sistema, espera_base=0)
                raise AssertionError('Deveria esgotar tentativas')
            except ErroSistema as e:
                assert e.tentativas == MAX_TENTATIVAS
            assert contador_sistema == MAX_TENTATIVAS
            # CNPJ alfanumérico atravessa extração -> validação -> formulário -> consulta.
            nf_alfa = dict(notas_geradas[0], numero='820002', cnpj='12.ABC.345/01DE-35')
            caminho = PASTA_SAIDA / 'teste_cnpj_alfanumerico.pdf'
            gerar_pdf_nf(nf_alfa, caminho)
            nota_alfa = extrair_nota(caminho)
            assert validar_nota(nota_alfa, set()) is None
            await robo.lancar(nota_alfa)
            assert ('820002', '12ABC34501DE35') in await ler_notas_do_erp(robo)
    finally:
        LAYOUT_ERP, SELETORES = layout_anterior, seletores_anteriores
    return medidas


medidas_interface = rodar(validar_interface())
benchmark_interface = pd.DataFrame(medidas_interface)
benchmark_interface.to_csv(PASTA_SAIDA / 'benchmark_interface.csv', index=False)
display(benchmark_interface.groupby(['layout', 'estrategia']).segundos.agg(['count', 'mean', 'median', 'std']))
print('Desafio 4: 12 lançamentos, layouts v1/v2 e ambas as estratégias aprovados.')
print('Falhas: 503 recuperado em 2 tentativas; negócio sem retentativa; sistema esgota em 3.')


# Casos sintéticos: medem aderência às regras, não acurácia de produção.
CASOS_CLASSIFICACAO = [
    ('Manutenção preventiva de frota', 'OPERACOES'),
    ('Frete Fortaleza-Recife', 'OPERACOES'),
    ('Lavagem de caminhões', 'OPERACOES'),
    ('Licença de software de GPS', 'TI'),
    ('Suporte ao sistema', 'TI'),
    ('Laudo estrutural', 'ENGENHARIA'),
    ('Sinalização e recapeamento', 'ENGENHARIA'),
    ('Serviço de limpeza e conservação', 'ADMINISTRATIVO'),
    ('Manutenção de ar-condicionado', 'ADMINISTRATIVO'),
    ('Consultoria diversa', None),
    ('Software para frota', None),
    ('GPS e software para frota', None),
    ('', None),
]
classificacoes = []
for descricao, esperado in CASOS_CLASSIFICACAO:
    centro, confianca = classificar_centro_custo(descricao)
    decisao = centro if confianca >= LIMIAR_CONFIANCA else None
    assert decisao == esperado, (descricao, centro, confianca)
    classificacoes.append(dict(descricao=descricao, esperado=esperado, centro=centro,
        confianca=confianca, decisao=decisao))
pd.DataFrame(classificacoes).to_csv(PASTA_SAIDA / 'classificacao.csv', index=False)

# Verifica integração com PDFs sem centro e perda de confirmação após gravar.
async def validar_extra_e_resposta_incerta():
    global PASTA_ENTRADA
    entrada_original = PASTA_ENTRADA
    entrada_teste = BASE / 'entrada_testes'
    entrada_teste.mkdir(exist_ok=True)
    for antigo in entrada_teste.glob('*.pdf'):
        antigo.unlink()
    for numero, descricao in [('830001', 'Manutenção de frota'), ('830002', 'Consultoria diversa'),
                               ('830003', 'Software para frota')]:
        gerar_pdf_nf(dict(notas_geradas[0], numero=numero, centro_custo=None,
                         descricao=descricao), entrada_teste / f'{numero}.pdf')
    try:
        PASTA_ENTRADA = entrada_teste
        # Simula ERP gravando com sucesso, mas a confirmação se perdendo para o robô.
        original = RoboERP.lancar
        chamadas = []
        async def resposta_perdida(self, nota):
            protocolo = await original(self, nota)
            chamadas.append(protocolo)
            raise ErroSistema('Confirmação perdida após gravar (injeção de teste)')
        with patch.object(RoboERP, 'lancar', resposta_perdida):
            resultados_extra = await executar_robo()
        assert [r.status for r in resultados_extra] == [STATUS_SUCESSO, STATUS_APROVACAO, STATUS_APROVACAO]
        assert resultados_extra[0].tentativas == 2
        assert len(chamadas) == 1, 'A retentativa não deve repetir a gravação'
        async with RoboERP() as robo:
            registros = await ler_registros_do_erp(robo)
            assert sum(n['numero'] == '830001' for n in registros) == 1
            assert not any(n['numero'] in {'830002', '830003'} for n in registros)
        return resultados_extra
    finally:
        PASTA_ENTRADA = entrada_original

resultados_extra = rodar(validar_extra_e_resposta_incerta())
pd.DataFrame([asdict(r) for r in resultados_extra]).to_csv(PASTA_SAIDA / 'teste_extra.csv', index=False)

# Benchmark do extrator mantido: mesma massa de 12 documentos, 5 repetições.
medidas_pdf = []
for repeticao in range(5):
    for pdf in sorted(PASTA_ENTRADA.glob('*.pdf')):
        inicio = time.perf_counter()
        try:
            extrair_nota(pdf)
            status = 'EXTRAIDO'
        except ErroNegocio:
            status = 'REJEITADO'
        medidas_pdf.append(dict(repeticao=repeticao + 1, arquivo=pdf.name,
            segundos=time.perf_counter() - inicio, status=status))
assert sum(m['status'] == 'EXTRAIDO' for m in medidas_pdf) == 55
pd.DataFrame(medidas_pdf).to_csv(PASTA_SAIDA / 'benchmark_pdf.csv', index=False)

# Artefatos legíveis por máquina para reproduzir a defesa das escolhas.
import platform
from importlib.metadata import version
metricas = {
    'ambiente': {'python': platform.python_version(), 'sistema': platform.platform(),
        'bibliotecas': {p: version(p) for p in ['playwright', 'pypdf', 'fpdf2', 'pandas', 'openpyxl']}},
    'lote': {'total': len(df_primeiro_lote), 'status': df_primeiro_lote.status.value_counts().to_dict(),
        'tempo_itens_s': float(df_primeiro_lote.duracao_s.sum()),
        'media_sucesso_s': float(df_primeiro_lote.loc[df_primeiro_lote.status == STATUS_SUCESSO, 'duracao_s'].mean()),
        'stp': float((df_primeiro_lote.status == STATUS_SUCESSO).mean())},
    'idempotencia': {'antes': len(antes), 'depois': len(depois), 'novos_lancamentos': 0},
    'interface': benchmark_interface.groupby(['layout', 'estrategia']).segundos.agg(['count', 'mean', 'median', 'std']).reset_index().to_dict('records'),
    'extracao': {'amostras': len(medidas_pdf), 'extraidos': 55, 'rejeitados': 5,
        'mediana_ms': statistics.median(m['segundos'] for m in medidas_pdf) * 1000},
    'classificacao': {'casos_sinteticos': len(classificacoes), 'aderencia_esperada': 1.0,
        'encaminhados_humano': sum(c['decisao'] is None for c in classificacoes)},
    'resiliencia': {'tentativas_503': 2, 'tentativas_negocio': 1, 'tentativas_falha_persistente': MAX_TENTATIVAS,
        'gravacoes_com_confirmacao_perdida': 1},
    'roi_hipotetico': {'horas_liberadas_mes': float(horas_economizadas),
        'economia_liquida_mes': float(economia_mes),
        'stp_equilibrio': CUSTO_MENSAL_ROBO / (NOTAS_POR_MES * MIN_HUMANO_POR_NOTA / 60 * CUSTO_HORA_ANALISTA)},
}
(PASTA_SAIDA / 'metricas.json').write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding='utf-8')
df_primeiro_lote.to_csv(PASTA_SAIDA / 'primeiro_lote.csv', index=False)
print('Desafio 5: 13 casos sintéticos aprovados; integração mantém notas incertas fora do ERP.')
print(json.dumps(metricas, ensure_ascii=False, indent=2))


# Encerramento após todos os testes e artefatos.
SERVIDOR_ERP.shutdown()
SERVIDOR_ERP.server_close()
print('ERP desligado. Artefatos em', PASTA_SAIDA.resolve())
