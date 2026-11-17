"""Gera coleção v2.1 com exemplos de respostas reais e testes de contrato."""
import datetime
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:8877'
items=[]
execucoes=[]

def item(nome,metodo,path,body=None,esperado=None,status=200,extra=None):
    request={'method':metodo,'header':[], 'url':'{{base_url}}'+path}
    data=None
    if body is not None:
        raw=json.dumps(body,ensure_ascii=False)
        data=raw.encode()
        request['header']=[{'key':'Content-Type','value':'application/json'}]
        request['body']={'mode':'raw','raw':raw,'options':{'raw':{'language':'json'}}}
    try:
        response=urlopen(Request(URL+path,data=data,headers={'Content-Type':'application/json'},method=metodo),timeout=15)
    except HTTPError as e:response=e
    raw_response=response.read().decode()
    obtido=json.loads(raw_response)
    checks=[f'pm.test("HTTP {status}", () => pm.response.to.have.status({status}));','const r = pm.response.json();']
    passou=response.status==status
    for key,value in (esperado or {}).items():
        checks.append(f'pm.test({json.dumps(key)}, () => pm.expect(r[{json.dumps(key)}]).to.eql({json.dumps(value)}));')
        passou=passou and obtido.get(key)==value
    checks+=extra or []
    example={'name':'Resposta observada — '+datetime.datetime.now().isoformat(timespec='seconds'),
        'originalRequest':request,'status':'OK' if response.status==200 else 'Erro esperado',
        'code':response.status,'header':[{'key':'Content-Type','value':'application/json'}],
        'body':raw_response,'_postman_previewlanguage':'json'}
    execucoes.append({'nome':nome,'metodo':metodo,'path':path,'entrada':body,
        'status_esperado':status,'status_obtido':response.status,'esperado':esperado,'obtido':obtido,'passou':passou})
    return {'name':nome,'request':request,'event':[{'listen':'test','script':{'type':'text/javascript','exec':checks}}], 'response':[example]}

visualizar='''pm.visualizer.set(`<h2>Bateria Python/Playwright: {{aprovados}} / {{total}}</h2><p>Falhas atuais: {{falhas}}</p><table border="1" cellpadding="6"><tr><th>ID</th><th>Cenário</th><th>Resultado</th></tr>{{#each cenarios}}<tr><td>{{id}}</td><td>{{descricao}}</td><td>{{passou}}</td></tr>{{/each}}</table>`, r);'''
resumo=json.loads((ROOT/'output/bateria/depois/resultados.json').read_text())
items.append({'name':'01 — Resumos e comparação antes/depois','item':[
    item('Saúde do adaptador local','GET','/saude',esperado={'status':'ok','api_do_erp':False}),
    item('Resultado completo — depois das correções','GET','/resultados/depois',esperado={'total':resumo['total'],'falhas':0},extra=[visualizar]),
    item('Histórico — falhas encontradas antes','GET','/resultados/antes',extra=[visualizar])
]})
items.append({'name':'02 — Evidências dos 60 cenários Python e Playwright','item':[
    item(f"{c['id']} — {c['descricao']}",'GET','/cenarios/'+c['id'],esperado={'id':c['id'],'passou':True},
         extra=['pm.test("Saída coincide com esperado", () => pm.expect(r.obtido).to.eql(r.esperado));'])
    for c in resumo['cenarios']
]})
aovivo=[]
for nome,cnpj,valido in [('Numérico válido','23.775.684/0001-07',True),('Alfanumérico válido','12.ABC.345/01DE-35',True),('DV errado','12.ABC.345/01DE-36',False),('Nulo',None,False),('Tipo numérico',23775684000107,False),('Zeros','0'*14,False)]:
    aovivo.append(item('CNPJ — '+nome,'POST','/validar/cnpj',{'cnpj':cnpj},{'valido':valido}))
for nome,campos,status in [('Válida',{},'ACEITO'),('Valor zero',{'valor':0},'EXCECAO_NEGOCIO'),('Valor negativo',{'valor':-1},'EXCECAO_NEGOCIO'),('Data impossível',{'data_emissao':'31/02/2026'},'EXCECAO_NEGOCIO'),('Limite exato',{'valor':50000},'ACEITO'),('Acima do limite',{'valor':50000.01},'PENDENTE_APROVACAO'),('Número vazio',{'numero':''},'EXCECAO_NEGOCIO'),('Centro desconhecido',{'centro_custo':'TI123'},'EXCECAO_NEGOCIO')]:
    aovivo.append(item('Nota — '+nome,'POST','/validar/nota',campos,{'status':status}))
for texto,destino in [('Manutenção de frota','OPERACOES'),('Software GPS','TI'),('Ecossistema de inovação','APROVACAO_HUMANA'),('Sistematização de documentos','APROVACAO_HUMANA'),('Software para frota','APROVACAO_HUMANA'),('Consultoria diversa','APROVACAO_HUMANA')]:
    aovivo.append(item('Classificação — '+texto,'POST','/classificar',{'descricao':texto},{'destino':destino}))
aovivo.append(item('Descrição de tipo inválido','POST','/classificar',{'descricao':42},status=400))
aovivo.append(item('Cenário inexistente','GET','/cenarios/INEXISTENTE',status=404))
items.append({'name':'03 — Validações Python ao vivo','item':aovivo})
collection={'info':{'name':'MBA RPA — Bateria de testes e evidências','schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
 'description':'60 cenários Python/Playwright com evidências reais, antes/depois e validações ao vivo. Inicie python scripts/servidor_testes.py. O adaptador local NÃO é uma API do ERP: o robô continua usando a interface. Pasta 02 consulta testes já executados; pasta 03 executa funções Python a cada requisição. Exemplos de resposta preservam saídas mesmo com servidor desligado.'},
 'variable':[{'key':'base_url','value':URL,'type':'string'}],'item':items}
(ROOT/'postman/MBA_RPA.postman_collection.json').write_text(json.dumps(collection,ensure_ascii=False,indent=2))
(ROOT/'output/bateria/postman_http.json').write_text(json.dumps({'total':len(execucoes),'aprovados':sum(e['passou'] for e in execucoes),'execucoes':execucoes},ensure_ascii=False,indent=2))
assert all(e['passou'] for e in execucoes),'Falhou uma verificação HTTP; consulte postman_http.json'
print(f'{len(execucoes)} requisições verificadas; coleção gerada com respostas reais.')
