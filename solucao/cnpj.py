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
