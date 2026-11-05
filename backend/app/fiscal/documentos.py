"""Validação de CNPJ (numérico e alfanumérico, IN RFB 2.229/2024) e CPF."""
import re

_PESOS_DV1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_DV2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def limpar_cnpj(valor: str) -> str:
    """Remove pontuação e põe em maiúsculas (o CNPJ alfanumérico aceita letras nas 12 primeiras posições)."""
    return re.sub(r"[^0-9A-Za-z]", "", valor or "").upper()


def _dv(base: str, pesos: list[int]) -> int:
    soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cnpj_valido(valor: str) -> bool:
    c = limpar_cnpj(valor)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c):
        return False
    if len(set(c)) == 1:
        return False
    return _dv(c[:12], _PESOS_DV1) == int(c[12]) and _dv(c[:13], _PESOS_DV2) == int(c[13])


def raiz_cnpj(cnpj: str) -> str:
    return limpar_cnpj(cnpj)[:8]


def cpf_valido(valor: str) -> bool:
    c = re.sub(r"\D", "", valor or "")
    if len(c) != 11 or len(set(c)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(c[n]):
            return False
    return True


def formatar_cnpj(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
