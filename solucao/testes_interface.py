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
