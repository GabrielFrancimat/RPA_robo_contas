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
