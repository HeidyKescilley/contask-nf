from datetime import datetime

from pydantic import BaseModel


class CertificadoOut(BaseModel):
    id: int | None = None
    titular_doc: str
    titular_nome: str
    tipo: str
    validade: datetime
    dias_restantes: int
    situacao: str  # ok|vence_30|vence_15|vence_7|vencido
    emissor: str | None = None
    responsavel: str | None = None


class BuscaResumo(BaseModel):
    situacao: str
    ultima_busca_em: datetime | None
    ultimo_erro: str | None
    tipo_consulta: str | None
    ultimo_nsu: int
    job_pendente: bool


class EmpresaOut(BaseModel):
    id: int
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    apelido: str | None
    uf: str | None
    municipio: str | None
    situacao_cadastral: str | None
    is_contabilidade: bool
    ativa: bool
    modo_certificado: str
    acesso: str  # proprio|mesma_raiz|procuracao|sem_certificado
    certificado: CertificadoOut | None
    busca: BuscaResumo
    total_notas: int
    pendencias: int
    criado_em: datetime


class EmpresaCriada(BaseModel):
    empresa: EmpresaOut
    avisos: list[str]


class EmpresaPatch(BaseModel):
    razao_social: str | None = None
    nome_fantasia: str | None = None
    apelido: str | None = None
    uf: str | None = None
    municipio: str | None = None
    ativa: bool | None = None
