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
