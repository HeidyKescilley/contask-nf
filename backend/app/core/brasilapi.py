"""Consulta de CNPJ na BrasilAPI. Falha nunca impede o cadastro: o usuário preenche à mão."""
import httpx

URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
TIMEOUT = 8.0


class BrasilApiErro(Exception):
    def __init__(self, mensagem: str, nao_encontrado: bool = False):
        super().__init__(mensagem)
        self.nao_encontrado = nao_encontrado


_MINUSCULAS = {"de", "do", "da", "dos", "das", "e", "d"}


def _titulo(nome: str | None) -> str | None:
    """BRASILIA -> Brasilia; SAO SEBASTIAO DO CAI -> Sao Sebastiao do Cai."""
    partes = (nome or "").strip().lower().split()
    if not partes:
        return None
    return " ".join(p if i and p in _MINUSCULAS else p.capitalize() for i, p in enumerate(partes))


def _cliente() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "ContaskNF/0.1", "Accept": "application/json"})


def consultar(cnpj: str, cliente: httpx.Client | None = None) -> dict:
    """Devolve os campos normalizados + o JSON bruto em `bruto`."""
    try:
        with (cliente or _cliente()) as c:
            r = c.get(URL.format(cnpj=cnpj))
    except httpx.HTTPError:
        raise BrasilApiErro("A BrasilAPI não respondeu. Preencha os dados manualmente.") from None
    if r.status_code == 404:
        raise BrasilApiErro("CNPJ não encontrado na BrasilAPI. Confira o número ou preencha manualmente.",
                            nao_encontrado=True)
    if r.status_code != 200:
        raise BrasilApiErro(f"A BrasilAPI respondeu com erro ({r.status_code}). Preencha os dados manualmente.")
    try:
        d = r.json()
    except ValueError:
        raise BrasilApiErro("Resposta inválida da BrasilAPI. Preencha os dados manualmente.") from None
    return {
        "cnpj": cnpj,
        "razao_social": (d.get("razao_social") or "").strip(),
        "nome_fantasia": (d.get("nome_fantasia") or "").strip() or None,
        "uf": d.get("uf") or None,
        "municipio": _titulo(d.get("municipio")),
        "situacao_cadastral": (d.get("descricao_situacao_cadastral") or "").strip().upper() or None,
        "bruto": d,
    }
