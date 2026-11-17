"""Adaptador LOCAL para inspecionar evidências e testar funções Python no Postman.
Não é uma API do ERP, nem substitui os testes de navegador.
"""
import argparse
import json
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'testes'))
from runtime import carregar

parser=argparse.ArgumentParser()
parser.add_argument('--porta',type=int,default=8877)
args=parser.parse_args()
m=carregar(ROOT/'output/postman_runtime')


def carregar_resultados(fase):
    return json.loads((ROOT/f'output/bateria/{fase}/resultados.json').read_text())


class Handler(BaseHTTPRequestHandler):
    def responder(self,codigo,dados):
        dados=json.dumps(dados,ensure_ascii=False,allow_nan=False,indent=2).encode()
        self.send_response(codigo)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(dados)))
        self.end_headers();self.wfile.write(dados)

    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/saude':return self.responder(200,{'status':'ok','servico':'Laboratório MBA — evidências e validações','api_do_erp':False})
        if path in ['/resultados/antes','/resultados/depois']:
            return self.responder(200,carregar_resultados(path.split('/')[-1]))
        if path.startswith('/cenarios/'):
            ident=path.split('/')[-1]
            for c in carregar_resultados('depois')['cenarios']:
                if c['id']==ident:return self.responder(200,c)
            return self.responder(404,{'erro':'Cenário inexistente'})
        return self.responder(404,{'erro':'Rota inexistente'})

    def do_POST(self):
        try:
            tamanho=int(self.headers.get('Content-Length',0))
            if not 0<tamanho<=10000:raise ValueError('Corpo deve ter de 1 a 10000 bytes')
            def invalido(v):raise ValueError(f'JSON não finito: {v}')
            dados=json.loads(self.rfile.read(tamanho),parse_constant=invalido)
            if not isinstance(dados,dict):raise ValueError('Objeto JSON obrigatório')
            path=urlparse(self.path).path
            if path=='/validar/cnpj':
                return self.responder(200,{'valido':m.cnpj_valido_v2(dados.get('cnpj'))})
            if path=='/classificar':
                descricao=dados.get('descricao')
                if not isinstance(descricao,str):raise ValueError('descricao deve ser texto')
                cc,confianca=m.classificar_centro_custo(descricao)
                return self.responder(200,{'centro':cc,'confianca':confianca,
                    'destino':cc if cc and confianca>=m.LIMIAR_CONFIANCA else 'APROVACAO_HUMANA',
                    'versao':m.VERSAO_CLASSIFICADOR})
            if path=='/validar/nota':
                campos=dict(arquivo='postman.pdf',numero='950001',data_emissao='01/10/2026',
                    prestador='Fornecedor de teste',cnpj='23.775.684/0001-07',descricao='Serviço',centro_custo='TI',valor=100.)
                if not set(dados)<=set(campos):raise ValueError('Campo desconhecido')
                campos.update(dados)
                try:
                    status=m.validar_nota(m.NotaFiscal(**campos),set()) or 'ACEITO'
                    return self.responder(200,{'status':status})
                except m.ErroNegocio as e:
                    return self.responder(200,{'status':m.STATUS_NEGOCIO,'motivo':str(e)})
            return self.responder(404,{'erro':'Rota inexistente'})
        except (ValueError,TypeError,UnicodeDecodeError) as e:
            return self.responder(400,{'erro':str(e)})

server=ThreadingHTTPServer(('127.0.0.1',args.porta),Handler)
print(f'Adaptador de testes: http://127.0.0.1:{args.porta}',flush=True)
try:server.serve_forever()
finally:
    server.server_close();m.SERVIDOR_ERP.shutdown();m.SERVIDOR_ERP.server_close()
