"""Monitoramento dos RPS (numeração de DPS liberada pelo ISSNet do DF).

Ciclo de cada número:
- disponivel: está na lista de ConsultarDpsDisponivel;
- reservado: uma nota do Contask ficou com ele (gravado ANTES do envio). Fica com a mesma nota enquanto
  ela estiver rejeitada ou pendente, porque o "corrigir e reenviar" usa o mesmo número;
- usado: a nota foi autorizada;
- usado_fora: sumiu da lista sem nota do Contask, ou seja, foi usado no portal do ISSNet.

Só a sincronização completa (todas as páginas lidas sem erro) marca um número como usado_fora.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.emissor.issnet import mensagens
from app.emissor.issnet.soap import ClienteIssnet, ErroIssnet
from app.models import RpsDisponivel, SincronizacaoRps, agora

log = logging.getLogger("contask.emissor.rps")

POR_PAGINA = 50
MAX_PAGINAS = 2000       # 100 mil números: acima disso algo está errado na paginação
LIMITE_MINIMO = 10       # alerta de "acabando" nunca abaixo disso
VALIDADE_SINCRONIZACAO = timedelta(hours=1)
FIM_DA_LISTA = "E319"    # "Página não encontrada": acabou a lista


class SemRps(Exception):
    """Não há número liberado: a empresa precisa pedir mais RPS no ISSNet."""


MSG_SEM_RPS = ("Esta empresa não tem RPS disponível no ISSNet do DF. Peça uma nova faixa de RPS no portal do "
               "ISSNet (com o certificado da empresa) e clique em \"Atualizar RPS\" na página da empresa.")


def _lidos(cli: ClienteIssnet, cnpj: str, im: str) -> list[mensagens.Rps]:
    vistos: list[mensagens.Rps] = []
    conhecidos: set[mensagens.Rps] = set()
    for pagina in range(1, MAX_PAGINAS + 1):
        r = cli.chamar("ConsultarDpsDisponivel", mensagens.consultar_dps_disponivel(cnpj, im, pagina))
        if r.erros and all(x.get("codigo") == FIM_DA_LISTA for x in r.erros):
            # Visto na produção: com exatamente 50 números, a página 2 responde E319. Na página 1, lista vazia.
            # Se a leitura estiver errada, o número volta a "disponivel" na próxima sincronização.
            return vistos
        if r.erros:
            raise ErroIssnet("O ISSNet recusou a consulta de RPS: " + mensagens.texto_erros(r.erros))
        lote, _ = mensagens.dps_disponiveis(r)
        novos = [x for x in lote if x not in conhecidos]
        vistos += novos
        conhecidos.update(novos)
        if len(lote) < POR_PAGINA or not novos:
            return vistos
    raise ErroIssnet(f"A lista de RPS passou de {MAX_PAGINAS} páginas; a sincronização foi interrompida.")


def sincronizar(db: Session, empresa_id: int, cnpj: str, im: str, ambiente: int, cli: ClienteIssnet) -> SincronizacaoRps:
    """Lê todas as páginas de ConsultarDpsDisponivel e atualiza a tabela. Erros ficam gravados, sem exceção."""
    sinc = db.get(SincronizacaoRps, (empresa_id, ambiente)) or SincronizacaoRps(empresa_id=empresa_id, ambiente=ambiente,
                                                                                disponiveis=0)
    db.add(sinc)
    try:
        lidos = _lidos(cli, cnpj, im)
    except ErroIssnet as ex:
        sinc.erro = str(ex)
        db.commit()
        log.warning("RPS da empresa %s não sincronizados: %s", empresa_id, ex)
        return sinc
    agora_ = agora()
    lista = {(x.serie, x.numero) for x in lidos}
    atuais = {(r.serie, r.numero): r for r in db.scalars(
        select(RpsDisponivel).where(RpsDisponivel.empresa_id == empresa_id, RpsDisponivel.ambiente == ambiente))}
    for chave in lista:
        r = atuais.get(chave)
        if r is None:
            db.add(RpsDisponivel(empresa_id=empresa_id, ambiente=ambiente, serie=chave[0], numero=chave[1],
                                 situacao="disponivel", visto_em=agora_))
            continue
        r.visto_em = agora_
        if r.situacao == "usado_fora":
            r.situacao = "disponivel"  # voltou para a lista: está livre
    for chave, r in atuais.items():
        if chave not in lista and r.situacao == "disponivel":
            r.situacao = "usado_fora"
    sinc.sincronizado_em, sinc.erro = agora_, None
    db.flush()
    sinc.disponiveis = _contar(db, empresa_id, ambiente, "disponivel")
    db.commit()
    return sinc


def ultima_sincronizacao(db: Session, empresa_id: int, ambiente: int) -> SincronizacaoRps | None:
    return db.get(SincronizacaoRps, (empresa_id, ambiente))


def precisa_sincronizar(db: Session, empresa_id: int, ambiente: int) -> bool:
    sinc = db.get(SincronizacaoRps, (empresa_id, ambiente))
    return sinc is None or sinc.sincronizado_em is None or agora() - _aware(sinc.sincronizado_em) > VALIDADE_SINCRONIZACAO


def _aware(dt):
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _contar(db: Session, empresa_id: int, ambiente: int, situacao: str) -> int:
    return db.scalar(select(func.count()).select_from(RpsDisponivel).where(
        RpsDisponivel.empresa_id == empresa_id, RpsDisponivel.ambiente == ambiente,
        RpsDisponivel.situacao == situacao)) or 0


def reservar(db: Session, empresa_id: int, ambiente: int, nota_id: int | None = None) -> RpsDisponivel:
    """Menor número disponível (série, número). Quem chama segura a trava da empresa e faz o commit."""
    r = db.scalar(select(RpsDisponivel).where(
        RpsDisponivel.empresa_id == empresa_id, RpsDisponivel.ambiente == ambiente,
        RpsDisponivel.situacao == "disponivel").order_by(RpsDisponivel.serie, RpsDisponivel.numero).limit(1))
    if r is None:
        raise SemRps(MSG_SEM_RPS)
    r.situacao, r.nota_id = "reservado", nota_id
    return r


def concluir(db: Session, nota_id: int, autorizada: bool) -> None:
    """Nota autorizada: o número vira usado. Rejeitada ou pendente: continua reservado para o reenvio."""
    if not autorizada:
        return
    for r in db.scalars(select(RpsDisponivel).where(RpsDisponivel.nota_id == nota_id)):
        r.situacao = "usado"


def liberar(db: Session, nota_id: int) -> None:
    """Nota descartada sem nunca ter virado NFS-e: o número volta a ficar disponível."""
    for r in db.scalars(select(RpsDisponivel).where(RpsDisponivel.nota_id == nota_id,
                                                    RpsDisponivel.situacao == "reservado")):
        r.situacao, r.nota_id = "disponivel", None


@dataclass
class Resumo:
    disponiveis: int
    reservados: int
    usados_fora: int
    consumo_30_dias: int
    limite_alerta: int
    nivel: str                # ok | baixo | zerado | sem_dados
    faixas: list[dict]        # [{serie, de, ate, quantidade}]
    sincronizado_em: object
    erro: str | None

    def como_dict(self) -> dict:
        d = self.__dict__.copy()
        d["sincronizado_em"] = self.sincronizado_em.isoformat() if self.sincronizado_em else None
        return d


def _faixas(numeros: list[tuple[str, int]]) -> list[dict]:
    """Agrupa números consecutivos da mesma série: 1,2,3,7 -> [1–3], [7–7]."""
    saida: list[dict] = []
    for serie, n in sorted(numeros, key=lambda x: (int(x[0]), x[1])):
        ult = saida[-1] if saida else None
        if ult and ult["serie"] == serie and ult["ate"] == n - 1:
            ult["ate"], ult["quantidade"] = n, ult["quantidade"] + 1
        else:
            saida.append({"serie": serie, "de": n, "ate": n, "quantidade": 1})
    return saida


def resumo(db: Session, empresa_id: int, ambiente: int) -> Resumo:
    base = select(RpsDisponivel).where(RpsDisponivel.empresa_id == empresa_id, RpsDisponivel.ambiente == ambiente)
    linhas = list(db.scalars(base))
    disp = [(r.serie, r.numero) for r in linhas if r.situacao == "disponivel"]
    desde = agora() - timedelta(days=30)
    consumo = sum(1 for r in linhas if r.situacao in ("usado", "usado_fora") and _aware(r.atualizado_em) >= desde)
    limite = max(LIMITE_MINIMO, consumo)
    sinc = db.get(SincronizacaoRps, (empresa_id, ambiente))
    if sinc is None or sinc.sincronizado_em is None:
        nivel = "sem_dados"
    elif not disp:
        nivel = "zerado"
    elif len(disp) < limite:
        nivel = "baixo"
    else:
        nivel = "ok"
    return Resumo(
        disponiveis=len(disp), reservados=sum(1 for r in linhas if r.situacao == "reservado"),
        usados_fora=sum(1 for r in linhas if r.situacao == "usado_fora"), consumo_30_dias=consumo,
        limite_alerta=limite, nivel=nivel, faixas=_faixas(disp),
        sincronizado_em=sinc.sincronizado_em if sinc else None, erro=sinc.erro if sinc else None,
    )
