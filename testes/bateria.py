"""Bateria adversarial com registros de entrada, expectativa, saída e traceback."""
import argparse
import asyncio
import dataclasses
import datetime
import json
import math
import time
import traceback
from pathlib import Path
from unittest.mock import patch

from runtime import carregar, ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--fase', choices=['antes', 'depois'], required=True)
args = parser.parse_args()
OUT = ROOT / 'output/bateria' / args.fase
OUT.mkdir(parents=True, exist_ok=True)
arquivo_notebook = (OUT / 'notebook_testado.ipynb') if args.fase == 'antes' else ROOT / 'RPA_Contas_a_Pagar_Resolvido.ipynb'
m = carregar(OUT / 'lab', notebook=arquivo_notebook)
registros = []


def registrar(ident, grupo, descricao, entrada, esperado, func):
    inicio = time.perf_counter()
    erro = None
    try:
        atual = func()
        passou = atual == esperado
    except Exception as e:
        atual = {'excecao': type(e).__name__, 'mensagem': str(e)}
        erro = traceback.format_exc()
        passou = False
    r = dict(id=ident, grupo=grupo, descricao=descricao, entrada=entrada,
             esperado=esperado, obtido=atual, passou=passou,
             duracao_ms=round((time.perf_counter()-inicio)*1000, 3))
    if erro:
        r['traceback'] = erro
    registros.append(r)
    print(ident, 'PASS' if passou else 'FAIL', descricao, flush=True)


async def registrar_async(ident, grupo, descricao, entrada, esperado, func):
    inicio = time.perf_counter()
    try:
        atual = await func()
        erro = None
    except Exception as e:
        atual = {'excecao': type(e).__name__, 'mensagem': str(e)}
        erro = traceback.format_exc()
    r = dict(id=ident, grupo=grupo, descricao=descricao, entrada=entrada,
             esperado=esperado, obtido=atual, passou=atual == esperado,
             duracao_ms=round((time.perf_counter()-inicio)*1000,3))
    if erro:
        r['traceback'] = erro
    registros.append(r)
    print(ident, 'PASS' if r['passou'] else 'FAIL', descricao, flush=True)


validos = ['23.775.684/0001-07', '12.ABC.345/01DE-35', '12abc34501de35', ' 12.ABC.345/01DE-35 ']
invalidos = ['12.ABC.345/01DE-36', '', '0'*14, '1'*14, '12ABC34501DEAA', '12@BC34501DE35',
             '123', '12ABC34501DE350', None, 23775684000107]
for i, v in enumerate(validos + invalidos):
    registrar(f'CNPJ-{i+1:02}', 'CNPJ', 'Normalização e validação de formato/DV', v,
              i < len(validos), lambda v=v: m.cnpj_valido_v2(v))

def propriedade():
    validos_ok = invalidos_ok = 0
    for _ in range(100):
        c = m.gerar_cnpj()
        validos_ok += m.cnpj_valido_v2(c)
        adulterado = c[:-1] + str((int(c[-1])+1)%10)
        invalidos_ok += not m.cnpj_valido_v2(adulterado)
    return [validos_ok, invalidos_ok]
registrar('CNPJ-15', 'CNPJ', '100 CNPJs gerados e 100 DVs adulterados', 'semente do laboratório', [100,100], propriedade)

base = m.NotaFiscal('teste.pdf','900001','01/10/2026','Fornecedor','23.775.684/0001-07','Serviço','TI',100.)
def validar(**campos):
    nota = dataclasses.replace(base, **campos)
    try:
        return m.validar_nota(nota, set()) or 'ACEITO'
    except m.ErroNegocio:
        return 'REJEITADO'

casos = [({'valor':0},'REJEITADO'),({'valor':-0.01},'REJEITADO'),
         ({'valor':float('nan')},'REJEITADO'),({'valor':float('inf')},'REJEITADO'),
         ({'valor':-float('inf')},'REJEITADO'),({'valor':50000},'ACEITO'),
         ({'valor':50000.01},m.STATUS_APROVACAO),({'data_emissao':'31/02/2026'},'REJEITADO'),
         ({'data_emissao':'2026-10-01'},'REJEITADO'),({'numero':''},'REJEITADO'),
         ({'prestador':'   '},'REJEITADO'),({'cnpj':'12.ABC.345/01DE-36'},'REJEITADO')]
for i,(campos,esperado) in enumerate(casos):
    registrar(f'REGRA-{i+1:02}', 'Regras', 'Limites e campos obrigatórios', {k:str(v) for k,v in campos.items()}, esperado,
              lambda c=campos: validar(**c))

def duplicidade():
    vistas=set()
    m.validar_nota(base,vistas)
    try:
        m.validar_nota(base,vistas)
        return 'ACEITO'
    except m.ErroNegocio:
        return 'REJEITADO'
registrar('REGRA-13','Regras','Duplicidade dentro do lote','mesma nota duas vezes','REJEITADO',duplicidade)

def rejeicao_nao_reserva():
    vistas=set()
    try:
        m.validar_nota(dataclasses.replace(base,valor=-1),vistas)
    except m.ErroNegocio:
        pass
    return len(vistas)
registrar('REGRA-14','Regras','Nota inválida não reserva chave','valor=-1',0,rejeicao_nao_reserva)

for i,(texto,esperado) in enumerate([
    ('Manutenção de frota','OPERACOES'),('LICENÇA DE SOFTWARE GPS','TI'),
    ('Laudo estrutural','ENGENHARIA'),('Limpeza e conservação','ADMINISTRATIVO'),
    ('Consultoria diversa',None),('Software para frota',None),('GPS e software para frota',None),
    ('Ecossistema de inovação',None),('Sistematização de documentos',None),('',None)]):
    def classificar(t=texto):
        cc, conf=m.classificar_centro_custo(t)
        return cc if conf>=m.LIMIAR_CONFIANCA else None
    registrar(f'CLASSE-{i+1:02}','Classificação','Palavras, ambiguidade e falsos positivos',texto,esperado,classificar)

# PDFs reais gerados com fpdf2, lidos com pypdf.
fixture=dict(m.notas_geradas[0],numero='900001',valor=100,cnpj=base.cnpj,centro_custo='TI')
def pdf_campo(campos,acao):
    p=OUT/'documento.pdf'
    m.gerar_pdf_nf(dict(fixture,**campos),p)
    try:
        nota=m.extrair_nota(p)
        return acao(nota)
    except m.ErroNegocio:
        return 'REJEITADO'
for ident,campos,esperado,acao in [
    ('PDF-01',{},100,lambda n:n.valor),
    ('PDF-02',{'valor':None},'REJEITADO',lambda n:'ACEITO'),
    ('PDF-03',{'centro_custo':None},'',lambda n:n.centro_custo),
    ('PDF-04',{'centro_custo':'TI123'},'TI123',lambda n:n.centro_custo),
    ('PDF-05',{'cnpj':'12.ABC.345/01DE-35'},'12.ABC.345/01DE-35',lambda n:n.cnpj),
    ('PDF-06',{'valor':12345.67},12345.67,lambda n:n.valor)]:
    registrar(ident,'PDF','Extração real sem truncamento silencioso',campos,esperado,lambda c=campos,a=acao:pdf_campo(c,a))
def pdf_corrompido():
    p=OUT/'corrompido.pdf';p.write_bytes(b'arquivo danificado')
    try:m.extrair_nota(p);return 'ACEITO'
    except m.ErroNegocio:return 'REJEITADO'
registrar('PDF-07','PDF','PDF corrompido vira exceção de negócio','bytes inválidos','REJEITADO',pdf_corrompido)

async def ui():
    async with m.RoboERP() as robo:
        async def vazia():return len(await m.ler_notas_do_erp(robo))
        await registrar_async('UI-01','Interface','Tabela inicialmente vazia','ERP isolado',0,vazia)
        for layout in ['v1','v2']:
            async def lancar(layout=layout):
                m.LAYOUT_ERP=layout
                nota=dataclasses.replace(base,numero='910001' if layout=='v1' else '910002')
                p=await robo.lancar(nota)
                return p.startswith('AP-') and (nota.numero,m.limpar_cnpj(nota.cnpj)) in await m.ler_notas_do_erp(robo)
            await registrar_async('UI-02' if layout=='v1' else 'UI-03','Interface','Lançamento por rótulos',layout,True,lancar)
        async def sessao():
            await robo.page.context.clear_cookies()
            return len(await m.ler_notas_do_erp(robo))
        await registrar_async('UI-04','Interface','Sessão expirada exige novo login','cookies apagados',2,sessao)
        async def layout_tabela():
            async def route(r):
                await r.fulfill(status=200,body='<table id="tblNotas"><tr><th>NF</th><th>Protocolo</th><th>CNPJ</th><th>Fornecedor</th><th>Valor</th><th>CC</th></tr><tr><td>910001</td><td>AP-1</td><td>23775684000107</td><td>A</td><td>100,00</td><td>TI</td></tr></table>',content_type='text/html')
            await robo.page.route('**/notas',route)
            try:
                try:await m.ler_registros_do_erp(robo);return 'ACEITO'
                except m.ErroSistema:return 'REJEITADO'
            finally:await robo.page.unroute('**/notas',route)
        await registrar_async('UI-05','Interface','Colunas trocadas não podem produzir leitura errada','NF e protocolo invertidos','REJEITADO',layout_tabela)
        async def rede():
            contador=0
            async def route(r):
                nonlocal contador
                contador+=1
                if contador==1:await r.abort('connectionreset')
                else:await r.continue_()
            await robo.page.route('**/notas',route)
            try:
                notas,tentativas=await m.com_retentativas(m.ler_notas_do_erp,robo,espera_base=0)
                return {'registros':len(notas),'tentativas':tentativas}
            finally:await robo.page.unroute('**/notas',route)
        await registrar_async('UI-06','Interface','Conexão interrompida é recuperada','primeiro GET abortado',{'registros':2,'tentativas':2},rede)
        async def erro_503():
            contador=0
            async def route(r):
                nonlocal contador
                contador+=1
                if contador<3:await r.fulfill(status=503,body='indisponível')
                else:await r.continue_()
            await robo.page.route('**/notas',route)
            try:
                notas,tentativas=await m.com_retentativas(m.ler_notas_do_erp,robo,espera_base=0)
                return [len(notas),tentativas]
            finally:await robo.page.unroute('**/notas',route)
        await registrar_async('UI-07','Interface','Duas falhas 503 e recuperação','503,503,200',[2,3],erro_503)
    async def login_falha():
        robo=m.RoboERP()
        async def negar(self):raise m.ErroNegocio('Credencial inválida simulada')
        try:
            with patch.object(m.RoboERP,'login',negar):
                try:await robo.__aenter__()
                except m.ErroNegocio:pass
            return not robo.browser.is_connected()
        finally:
            if hasattr(robo,'browser') and robo.browser.is_connected():await robo.__aexit__(None,None,None)
    await registrar_async('UI-08','Interface','Falha no login libera o navegador','login rejeitado',True,login_falha)

    # Lote misto, com erro de sistema e falha adicional ao capturar evidência.
    async def lote():
        for p in m.PASTA_ENTRADA.glob('*.pdf'):p.unlink()
        for numero,valor in [('920001',100),('920002',100),('920003',-1)]:
            m.gerar_pdf_nf(dict(fixture,numero=numero,valor=valor),m.PASTA_ENTRADA/f'{numero}.pdf')
        original=m.RoboERP.lancar
        async def falhar(self,nota):
            if nota.numero=='920001':raise m.ErroSistema('Falha persistente simulada')
            return await original(self,nota)
        async def captura(self,nome):raise OSError('Disco indisponível simulado')
        with patch.object(m.RoboERP,'lancar',falhar),patch.object(m.RoboERP,'evidencia',captura):
            rs=await m.executar_robo()
        return [r.status for r in rs]
    await registrar_async('LOTE-01','Orquestração','Erro e screenshot falho não interrompem próximos itens','3 PDFs',
        [m.STATUS_SISTEMA,m.STATUS_SUCESSO,m.STATUS_NEGOCIO],lote)
    async def vazio():
        for p in m.PASTA_ENTRADA.glob('*.pdf'):p.unlink()
        return len(await m.executar_robo())
    await registrar_async('LOTE-02','Orquestração','Fila vazia','0 PDFs',0,vazio)
    async def perda():
        m.gerar_pdf_nf(dict(fixture,numero='920004'),m.PASTA_ENTRADA/'920004.pdf')
        original=m.RoboERP.lancar
        contador=0
        async def gravar_sem_resposta(self,nota):
            nonlocal contador
            contador+=1
            await original(self,nota)
            raise m.ErroSistema('Resposta perdida após commit')
        with patch.object(m.RoboERP,'lancar',gravar_sem_resposta):rs=await m.executar_robo()
        return [rs[0].status,rs[0].tentativas,contador]
    await registrar_async('LOTE-03','Orquestração','Perda da resposta não duplica POST','gravação seguida de erro',
        [m.STATUS_SUCESSO,2,1],perda)
    async def repetir():
        rs=await m.executar_robo()
        return [rs[0].status,rs[0].tentativas]
    await registrar_async('LOTE-04','Orquestração','Reexecução ignora nota existente','mesma entrada',
        [m.STATUS_NEGOCIO,0],repetir)

try:
    asyncio.run(ui())
finally:
    m.SERVIDOR_ERP.shutdown();m.SERVIDOR_ERP.server_close()

for ident,quantidade in [('EMAIL-01',0),('EMAIL-02',1)]:
    def email(q=quantidade):
        import pandas as pd
        from openpyxl import Workbook
        p=OUT/'anexo.xlsx';Workbook().save(p)
        df=pd.DataFrame([dataclasses.asdict(m.Resultado('nota.pdf',m.STATUS_SUCESSO))]*q,
                        columns=[f.name for f in dataclasses.fields(m.Resultado)])
        arquivo=m.gerar_email(df,p)
        msg=m.BytesParser(policy=m.policy.default).parsebytes(arquivo.read_bytes())
        return list(msg.iter_attachments())[0].get_payload(decode=True)==p.read_bytes() and 'Nenhuma pendência' in msg.get_body().get_content()
    registrar(ident,'E-mail','Lote vazio ou sem pendências, anexo íntegro',{'notas':quantidade},True,email)

relatorio={'fase':args.fase,'executado_em':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'notebook_sha256': __import__('hashlib').sha256(arquivo_notebook.read_bytes()).hexdigest(),
    'total':len(registros),'aprovados':sum(r['passou'] for r in registros),
    'falhas':sum(not r['passou'] for r in registros),'cenarios':registros}
(OUT/'resultados.json').write_text(json.dumps(relatorio,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in relatorio.items() if k!='cenarios'},ensure_ascii=False))
