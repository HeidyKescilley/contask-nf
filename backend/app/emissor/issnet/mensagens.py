"""XML de dados dos métodos do ISSNet (namespace da NFS-e nacional) e leitura das respostas.

Estruturas conferidas no schema_v101.xsd da Nota Control:
- tcIdentificacaoDps = NumDPS, SerieDPS (nessa ordem);
- tcIdentificacaoPessoaEmpresaComIM = CNPJ|CPF + IM obrigatória;
- GerarNfseEnvio = DPS (TCDPS); GerarNfseResposta = ListaNfse/CompNfse | ListaMensagemRetorno;
- CompNfse = NFSe (TCNFSe, o mesmo leiaute nacional) + ListaEvento opcional;
- CancelarNfseEnvio = pedRegEvento; CancelarNfseResposta = ListaEvento | ListaMensagemRetorno.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from app.emissor.issnet.soap import NS_NFSE, Retorno, filhos, local

N = f"{{{NS_NFSE}}}"


def _e(pai, tag, texto=None):
    el = etree.SubElement(pai, N + tag)
    if texto is not None:
        el.text = str(texto)
    return el


def _raiz(tag: str):
    return etree.Element(N + tag, nsmap={None: NS_NFSE})


def _prestador(pai, cnpj: str, im: str, tag: str = "Prestador"):
    p = _e(pai, tag)
    _e(p, "CNPJ" if len(cnpj) == 14 else "CPF", cnpj)
    _e(p, "IM", im)
    return p


def _texto(el) -> str:
    return etree.tostring(el, encoding="unicode")


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------

def gerar_nfse(dps_assinada) -> str:
    """GerarNfseEnvio com a DPS já assinada (a assinatura fica dentro da DPS)."""
    raiz = _raiz("GerarNfseEnvio")
    raiz.append(etree.fromstring(etree.tostring(dps_assinada)))
    return _texto(raiz)


def cancelar_nfse(pedido_assinado) -> str:
    raiz = _raiz("CancelarNfseEnvio")
    raiz.append(etree.fromstring(etree.tostring(pedido_assinado)))
    return _texto(raiz)


def consultar_nfse_por_dps(cnpj: str, im: str, serie: str, numero: int) -> str:
    raiz = _raiz("ConsultarNfseDpsEnvio")
    ident = _e(raiz, "IdentificacaoDps")
    _e(ident, "NumDPS", int(numero))
    _e(ident, "SerieDPS", int(serie))
    _prestador(raiz, cnpj, im)
    return _texto(raiz)


def consultar_dps_disponivel(cnpj: str, im: str, pagina: int = 1) -> str:
    raiz = _raiz("ConsultarDpsDisponivelEnvio")
    _prestador(raiz, cnpj, im)
    _e(raiz, "Pagina", pagina)
    return _texto(raiz)


def consultar_dados_cadastrais(cnpj: str, im: str) -> str:
    raiz = _raiz("ConsultarDadosCadastraisEnvio")
    _prestador(raiz, cnpj, im)
    return _texto(raiz)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rps:
    serie: str
    numero: int


def _filho(el, nome: str):
    return next((c for c in filhos(el) if local(c) == nome), None)


def _txt(el, nome: str) -> str | None:
    c = _filho(el, nome) if el is not None else None
    return (c.text or "").strip() if c is not None and c.text else None


def dps_disponiveis(r: Retorno) -> tuple[list[Rps], int | None]:
    """(RPS disponíveis desta página, número da página informada pelo ISSNet)."""
    lista = next((e for e in r.xml.iter() if local(e) == "ListaDpsDisponivel"), None)
    if lista is None:
        return [], None
    saida = []
    for d in filhos(lista):
        if local(d) != "DpsDisponivel":
            continue
        num, serie = _txt(d, "NumDPS"), _txt(d, "SerieDPS")
        if num and serie and num.isdigit() and serie.isdigit():
            saida.append(Rps(serie=str(int(serie)), numero=int(num)))
    pagina = _txt(lista, "Pagina")
    return saida, int(pagina) if pagina and pagina.isdigit() else None


def nfses(r: Retorno) -> list[bytes]:
    """XML de cada NFS-e (elemento NFSe, leiaute nacional) contida em CompNfse."""
    saida = []
    for comp in (e for e in r.xml.iter() if local(e) == "CompNfse"):
        nf = _filho(comp, "NFSe")
        if nf is not None:
            saida.append(etree.tostring(nf, xml_declaration=True, encoding="UTF-8"))
    return saida


def eventos(r: Retorno) -> list[bytes]:
    lista = next((e for e in r.xml.iter() if local(e) == "ListaEvento"), None)
    if lista is None:
        return []
    return [etree.tostring(ev, xml_declaration=True, encoding="UTF-8") for ev in filhos(lista)]


def texto_erros(erros: list[dict]) -> str:
    return "; ".join(f"{x.get('codigo')}: {x.get('descricao')}" + (f" ({x['complemento']})" if x.get("complemento") else "")
                     for x in erros)
