"""Modelo de dados (seção 4 do plano). O banco é a fonte da verdade do status."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Certificado(Base):
    __tablename__ = "certificado"
    id: Mapped[int] = mapped_column(primary_key=True)
    titular_doc: Mapped[str] = mapped_column(String(14), index=True)
    titular_nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(8))  # e-CNPJ | e-CPF
    validade: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thumbprint: Mapped[str] = mapped_column(String(64), unique=True)
    pfx_cifrado_path: Mapped[str] = mapped_column(String(500))
    senha_cifrada: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (
        # Só uma empresa pode ser a contabilidade
        Index("ux_empresa_contabilidade", "is_contabilidade", unique=True,
              sqlite_where=text("is_contabilidade = 1")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True)
    razao_social: Mapped[str] = mapped_column(String(200))
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    apelido: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))
    municipio: Mapped[str | None] = mapped_column(String(100))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(50))
    dados_brasilapi: Mapped[dict | None] = mapped_column(JSON)
    is_contabilidade: Mapped[bool] = mapped_column(Boolean, default=False)
    modo_certificado: Mapped[str] = mapped_column(String(15), default="contabilidade")  # proprio|contabilidade
    certificado_id: Mapped[int | None] = mapped_column(ForeignKey("certificado.id", ondelete="SET NULL"))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class SyncEstado(Base):
    __tablename__ = "sync_estado"
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True)
    ultimo_nsu: Mapped[int] = mapped_column(Integer, default=0)
    # nunca_buscada|buscando|em_dia|sem_procuracao|erro_certificado|erro|limite_mes|limite_teste
    situacao: Mapped[str] = mapped_column(String(20), default="nunca_buscada")
    tipo_consulta: Mapped[str | None] = mapped_column(String(30))
    ultima_busca_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)


class DocumentoDfe(Base):
    """Registro de tudo que chegou do ADN."""
    __tablename__ = "documento_dfe"
    __table_args__ = (UniqueConstraint("empresa_id", "nsu", name="uq_documento_empresa_nsu"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"))
    nsu: Mapped[int] = mapped_column(Integer)
    chave: Mapped[str | None] = mapped_column(String(50), index=True)
    tipo_documento: Mapped[str] = mapped_column(String(20))
    tipo_evento: Mapped[str | None] = mapped_column(String(60))
    gerado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    xml_path: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))
    processado: Mapped[bool] = mapped_column(Boolean, default=False)
    erro_processamento: Mapped[str | None] = mapped_column(Text)


class Nota(Base):
    __tablename__ = "nota"
    __table_args__ = (
        UniqueConstraint("empresa_id", "chave", name="uq_nota_empresa_chave"),
        Index("ix_nota_empresa_papel_emissao", "empresa_id", "papel", "data_emissao"),
        Index("ix_nota_empresa_competencia_status", "empresa_id", "competencia", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"))
    chave: Mapped[str] = mapped_column(String(50))
    papel: Mapped[str] = mapped_column(String(15))  # prestada|tomada|intermediada|outra
    numero: Mapped[str | None] = mapped_column(String(20), index=True)
    serie: Mapped[str | None] = mapped_column(String(10))
    n_dps: Mapped[str | None] = mapped_column(String(20))
    emitente_doc: Mapped[str | None] = mapped_column(String(14))
    emitente_nome: Mapped[str | None] = mapped_column(String(200))
    emitente_uf: Mapped[str | None] = mapped_column(String(2))
    prestador_doc: Mapped[str | None] = mapped_column(String(14))
    tomador_doc: Mapped[str | None] = mapped_column(String(14))
    tomador_nome: Mapped[str | None] = mapped_column(String(200))
    valor_servico: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), index=True)
    valor_liquido: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_iss: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    data_emissao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    competencia: Mapped[date | None] = mapped_column(Date)
    municipio: Mapped[str | None] = mapped_column(String(100))
    c_stat: Mapped[str | None] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(15), default="autorizada")  # autorizada|cancelada|rejeitada
    status_detalhe: Mapped[str | None] = mapped_column(String(100))
    em_analise_fiscal: Mapped[bool] = mapped_column(Boolean, default=False)
    bloqueada: Mapped[bool] = mapped_column(Boolean, default=False)
    xml_path: Mapped[str | None] = mapped_column(String(500))
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    nsu: Mapped[int | None] = mapped_column(Integer)


class EventoNota(Base):
    """Sem FK obrigatória para a nota: o evento pode chegar antes dela."""
    __tablename__ = "evento_nota"
    __table_args__ = (Index("ix_evento_empresa_chave", "empresa_id", "chave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"))
    chave: Mapped[str] = mapped_column(String(50))
    codigo: Mapped[str | None] = mapped_column(String(6))
    descricao: Mapped[str | None] = mapped_column(String(200))
    data_evento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nsu: Mapped[int | None] = mapped_column(Integer)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documento_dfe.id", ondelete="SET NULL"))


class BuscaJob(Base):
    __tablename__ = "busca_job"
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(15))  # inicial|incremental|refazer
    status: Mapped[str] = mapped_column(String(15), default="fila", index=True)  # fila|rodando|pausado|concluido|erro|cancelado
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    docs_recebidos: Mapped[int] = mapped_column(Integer, default=0)
    notas_ok: Mapped[int] = mapped_column(Integer, default=0)
    eventos_ok: Mapped[int] = mapped_column(Integer, default=0)
    docs_com_erro: Mapped[int] = mapped_column(Integer, default=0)
    eventos_sem_nota: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_nsu: Mapped[int | None] = mapped_column(Integer)
    mensagem: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class BuscaLog(Base):
    __tablename__ = "busca_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("busca_job.id", ondelete="CASCADE"), index=True)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    nivel: Mapped[str] = mapped_column(String(10))
    mensagem: Mapped[str] = mapped_column(Text)


class Exportacao(Base):
    __tablename__ = "exportacao"
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    filtros: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(15), default="fila")
    total_notas: Mapped[int | None] = mapped_column(Integer)
    zip_path: Mapped[str | None] = mapped_column(String(500))
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Usuario(Base):
    """Pessoa do escritório que entra no sistema (servidor na internet)."""
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    senha_hash: Mapped[str] = mapped_column(String(300))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    ultimo_acesso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessaoUsuario(Base):
    """Sessão de login. Guarda só o SHA-256 do token do cookie."""
    __tablename__ = "sessao_usuario"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
