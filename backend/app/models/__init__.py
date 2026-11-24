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


class Convite(Base):
    """Código de uso único para cadastrar um escritório (CONTASK_CADASTRO=convite). Só o hash fica gravado."""
    __tablename__ = "convite"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_hash: Mapped[str] = mapped_column(String(64), unique=True)
    descricao: Mapped[str] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado: Mapped[bool] = mapped_column(Boolean, default=False)
    escritorio_id: Mapped[int | None] = mapped_column(ForeignKey("escritorio.id", ondelete="SET NULL"))


class Escritorio(Base):
    """Cliente que paga. Um usuário vê todas as empresas deste escritório."""
    __tablename__ = "escritorio"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    # contador: contabilidade com várias empresas clientes | empresa: a própria empresa, um CNPJ só (foco no emissor)
    tipo: Mapped[str] = mapped_column(String(10), default="contador", server_default="contador")
    # teste (teste grátis, até teste_ate) | ativo | suspenso (ninguém entra; buscas e recorrências param)
    situacao: Mapped[str] = mapped_column(String(10), default="ativo", server_default="ativo")
    teste_ate: Mapped[date | None] = mapped_column(Date)
    # Limite de XMLs novos por mês; vazio = o padrão do sistema (CONTASK_LIMITE_XMLS_MES), 0 = sem limite
    limite_xmls_mes: Mapped[int | None] = mapped_column(Integer)
    # Mensalidade: controle manual (a cobrança é feita fora do sistema)
    mensalidade: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    dia_vencimento: Mapped[int | None] = mapped_column(Integer)
    proximo_vencimento: Mapped[date | None] = mapped_column(Date)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=agora)


class EscritorioEvento(Base):
    """Histórico administrativo: situação, plano e pagamentos."""
    __tablename__ = "escritorio_evento"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    tipo: Mapped[str] = mapped_column(String(20))  # criado | situacao | plano | pagamento
    descricao: Mapped[str] = mapped_column(Text)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class Lead(Base):
    """Pedido feito por um formulário do site: teste grátis (conta criada na hora) ou oferta de campanha."""
    __tablename__ = "lead"
    id: Mapped[int] = mapped_column(primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    nome: Mapped[str] = mapped_column(String(200))  # escritório ou empresa
    # contabilidade | bpo | financeiro | nenhum
    segmento: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(200), index=True)
    telefone: Mapped[str] = mapped_column(String(20))
    origem: Mapped[str | None] = mapped_column(String(300))  # página e campanha (utm)
    ip: Mapped[str | None] = mapped_column(String(64))
    # conta_criada | email_existente | oferta | plano_personalizado
    resultado: Mapped[str] = mapped_column(String(20))
    escritorio_id: Mapped[int | None] = mapped_column(ForeignKey("escritorio.id", ondelete="SET NULL"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    # pendente | enviado | erro | sem_envio (e-mail do sistema não configurado)
    email_status: Mapped[str] = mapped_column(String(12), default="pendente")
    email_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_erro: Mapped[str | None] = mapped_column(String(300))
    # novo | em_contato | cliente | perdido (acompanhamento comercial)
    etapa: Mapped[str] = mapped_column(String(12), default="novo", server_default="novo")
    observacoes: Mapped[str | None] = mapped_column(Text)
    # Campanha do formulário: None (teste grátis) | black_friday (oferta paga, sem conta criada na hora)
    campanha: Mapped[str | None] = mapped_column(String(30))
    contato: Mapped[str | None] = mapped_column(String(200))  # nome da pessoa, quando o formulário pede
    # ate_100 | 100_500 | 500_1000 | acima_1000
    notas_mes: Mapped[str | None] = mapped_column(String(20))
    aceita_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))


class Visita(Base):
    """Visualização de página do site de vendas, sem cookie e sem dado pessoal.

    `visitante` é um resumo (HMAC) de IP + navegador + dia: conta pessoas por dia sem guardar o IP e sem
    permitir seguir alguém de um dia para o outro.
    """
    __tablename__ = "visita"
    id: Mapped[int] = mapped_column(primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    dia: Mapped[date] = mapped_column(Date, index=True)
    pagina: Mapped[str] = mapped_column(String(120))
    canal: Mapped[str] = mapped_column(String(60))  # utm_source, site de onde veio ou "direto"
    meio: Mapped[str | None] = mapped_column(String(60))  # utm_medium
    campanha: Mapped[str | None] = mapped_column(String(100))  # utm_campaign
    referencia: Mapped[str | None] = mapped_column(String(120))  # domínio de onde veio
    dispositivo: Mapped[str] = mapped_column(String(12))  # celular | computador
    visitante: Mapped[str] = mapped_column(String(16))


class Certificado(Base):
    __tablename__ = "certificado"
    __table_args__ = (
        UniqueConstraint("escritorio_id", "thumbprint", name="uq_certificado_escritorio_thumbprint"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    titular_doc: Mapped[str] = mapped_column(String(14), index=True)
    titular_nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(8))  # e-CNPJ | e-CPF
    validade: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thumbprint: Mapped[str] = mapped_column(String(64))
    pfx_cifrado_path: Mapped[str] = mapped_column(String(500))
    senha_cifrada: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (
        UniqueConstraint("escritorio_id", "cnpj", name="uq_empresa_escritorio_cnpj"),
        # Uma contabilidade por escritório
        Index("ux_empresa_contabilidade", "escritorio_id", unique=True,
              sqlite_where=text("is_contabilidade = 1")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    cnpj: Mapped[str] = mapped_column(String(14))
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
    # Só na contabilidade: segundo certificado de procurador (em geral o e-CPF do contador)
    certificado_extra_id: Mapped[int | None] = mapped_column(ForeignKey("certificado.id", ondelete="SET NULL"))
    # Empresa por procuração: o certificado da contabilidade que tem a procuração dela (descoberto na busca)
    certificado_procurador_id: Mapped[int | None] = mapped_column(ForeignKey("certificado.id", ondelete="SET NULL"))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    # Emite NFS-e pelo emissor do Contask (exige certificado próprio: procuração não assina DPS, E0718)
    emite_nfse: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class EmissorEmpresa(Base):
    """Dados de prestador para o emissor (grupo prest/regTrib da DPS e numeração)."""
    __tablename__ = "emissor_empresa"
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True)
    inscricao_municipal: Mapped[str | None] = mapped_column(String(15))
    # opSimpNac: 1 não optante | 2 MEI | 3 ME/EPP
    op_simples: Mapped[str] = mapped_column(String(1), default="1")
    # regApTribSN (só ME/EPP): 1 tudo pelo SN | 2 federais pelo SN, ISS fora | 3 tudo fora do SN
    reg_ap_trib_sn: Mapped[str | None] = mapped_column(String(1))
    # regEspTrib: 0 nenhum | 1 ato cooperado | 2 estimativa | 3 microempresa municipal | 4 notário | 5 autônomo | 6 sociedade de profissionais
    reg_esp_trib: Mapped[str] = mapped_column(String(1), default="0")
    serie: Mapped[str] = mapped_column(String(5), default="1")  # 00001–49999: aplicativo próprio
    proximo_numero: Mapped[int] = mapped_column(Integer, default=1)
    cod_municipio: Mapped[str | None] = mapped_column(String(7))  # IBGE do município emissor (cLocEmi)
    # Percentual aproximado de tributos (Lei 12.741). Para ME/EPP vai em pTotTribSN.
    percentual_tributos: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Só emite em produção com CONTASK_EMISSOR_PRODUCAO=true E esta liberação; senão, produção restrita.
    # Padrão: produção (decisão de 12/11/2026); a homologação é escolhida empresa por empresa.
    producao_liberada: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # simples | presumido | real (o Simples acrescenta o texto legal nas informações complementares)
    regime_tributario: Mapped[str | None] = mapped_column(String(10))
    # Texto fixo das informações complementares (dados bancários, observações): entra em toda nota da empresa
    texto_fixo: Mapped[str | None] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class NotaEmitida(Base):
    """NFS-e emitida pelo Contask (DPS enviada à Sefin Nacional) e o que aconteceu com ela."""
    __tablename__ = "nota_emitida"
    __table_args__ = (UniqueConstraint("ambiente", "id_dps", name="uq_nota_emitida_ambiente_id_dps"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    servico_id: Mapped[int | None] = mapped_column(ForeignKey("servico_emissor.id", ondelete="SET NULL"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    ambiente: Mapped[int] = mapped_column(Integer)  # 1 produção | 2 produção restrita
    serie: Mapped[str] = mapped_column(String(5))
    numero: Mapped[int] = mapped_column(Integer)
    id_dps: Mapped[str] = mapped_column(String(45))
    # enviando | autorizada | rejeitada | pendente (resultado desconhecido) | cancelada
    situacao: Mapped[str] = mapped_column(String(12), index=True)
    # nacional (Sefin Nacional) | issnet_df (webservice do ISSNet do DF, empresas fora do Simples)
    canal: Mapped[str] = mapped_column(String(10), default="nacional", server_default="nacional")
    competencia: Mapped[date] = mapped_column(Date)
    tomador: Mapped[dict | None] = mapped_column(JSON)  # cópia dos dados do tomador usados na nota
    # Tomador no exterior: grupo comExt (moeda, valor na moeda, modo...) e se é exportação de serviço
    comercio_exterior: Mapped[dict | None] = mapped_column(JSON)
    descricao: Mapped[str] = mapped_column(Text)
    ctribnac: Mapped[str] = mapped_column(String(6))
    cnbs: Mapped[str] = mapped_column(String(9))
    ctribmun: Mapped[str | None] = mapped_column(String(10))  # no ISSNet DF: código municipal de até 10 dígitos
    cindop: Mapped[str | None] = mapped_column(String(6))     # IBS/CBS (obrigatório no ISSNet DF)
    cclasstrib: Mapped[str | None] = mapped_column(String(6))
    cod_municipio_prestacao: Mapped[str] = mapped_column(String(7))
    valor_servico: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    desconto: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    iss_retido: Mapped[bool] = mapped_column(Boolean, default=False)
    aliquota_iss: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ret_pis: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    ret_cofins: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    ret_csll: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    ret_irrf: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    ret_cp: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    info_complementar: Mapped[str | None] = mapped_column(Text)
    # Resultado (lido da NFS-e autorizada)
    chave: Mapped[str | None] = mapped_column(String(50), index=True)
    numero_nfse: Mapped[str | None] = mapped_column(String(20))
    valor_iss: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_liquido: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    erros: Mapped[list | None] = mapped_column(JSON)  # [{codigo, descricao, complemento}]
    mensagem: Mapped[str | None] = mapped_column(Text)
    xml_dps_path: Mapped[str | None] = mapped_column(String(500))
    xml_nfse_path: Mapped[str | None] = mapped_column(String(500))
    xml_cancelamento_path: Mapped[str | None] = mapped_column(String(500))
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    autorizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorrente_id: Mapped[int | None] = mapped_column(ForeignKey("nota_recorrente.id", ondelete="SET NULL"))
    # Substituição: esta nota substitui a NFS-e subst_chave (grupo subst da DPS). Autorizada a substituta, a
    # original do Contask fica cancelada com substituida_por_id apontando para cá.
    subst_chave: Mapped[str | None] = mapped_column(String(50), index=True)
    subst_motivo: Mapped[str | None] = mapped_column(String(2))
    subst_justificativa: Mapped[str | None] = mapped_column(Text)
    substituida_por_id: Mapped[int | None] = mapped_column(ForeignKey("nota_emitida.id", ondelete="SET NULL"))


class RpsDisponivel(Base):
    """Numeração de DPS (RPS) liberada pelo ISSNet do DF para a empresa e o que aconteceu com cada número.

    No ISSNet a numeração é do fisco (manual v1.01, 5.2): a empresa só usa os números que o ISSNet lista em
    ConsultarDpsDisponivel. situacao: disponivel | reservado (nota criada, ainda sem resultado) | usado
    (virou nota no Contask) | usado_fora (sumiu da lista sem nota do Contask: usado no portal do ISSNet).
    """
    __tablename__ = "rps_disponivel"
    __table_args__ = (UniqueConstraint("empresa_id", "ambiente", "serie", "numero", name="uq_rps_empresa_numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    ambiente: Mapped[int] = mapped_column(Integer)
    serie: Mapped[str] = mapped_column(String(5))
    numero: Mapped[int] = mapped_column(Integer)
    situacao: Mapped[str] = mapped_column(String(12), default="disponivel", index=True)
    nota_id: Mapped[int | None] = mapped_column(ForeignKey("nota_emitida.id", ondelete="SET NULL"))
    visto_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)  # última vez na lista do ISSNet
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class SincronizacaoRps(Base):
    """Última leitura de ConsultarDpsDisponivel por empresa e ambiente (para o painel e os alertas)."""
    __tablename__ = "sincronizacao_rps"
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True)
    ambiente: Mapped[int] = mapped_column(Integer, primary_key=True)
    sincronizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disponiveis: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str | None] = mapped_column(Text)


class NotaRascunho(Base):
    """Nota preenchida e guardada para emitir depois (os campos do formulário de emissão, em JSON)."""
    __tablename__ = "nota_rascunho"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    dados: Mapped[dict] = mapped_column(JSON)
    # Última validação antes da transmissão: {pronta, erros, alertas, em}; apagada quando o rascunho muda
    validacao: Mapped[dict | None] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class NotaRecorrente(Base):
    """Nota emitida automaticamente todo mês no dia escolhido, com variáveis de data na descrição."""
    __tablename__ = "nota_recorrente"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    nome: Mapped[str] = mapped_column(String(120))
    dados: Mapped[dict] = mapped_column(JSON)          # campos da emissão, sem a competência
    dia: Mapped[int] = mapped_column(Integer)           # 1 a 31 (meses mais curtos: último dia)
    competencia: Mapped[str] = mapped_column(String(8), default="atual")  # atual | anterior (em relação à emissão)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    proxima_em: Mapped[date | None] = mapped_column(Date, index=True)
    ultima_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_nota_id: Mapped[int | None] = mapped_column(ForeignKey("nota_emitida.id", ondelete="SET NULL", use_alter=True))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class ServicoEmissor(Base):
    """Serviço cadastrado de uma empresa: descrição e códigos. Valor e tributos vêm na emissão."""
    __tablename__ = "servico_emissor"
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"), index=True)
    descricao: Mapped[str] = mapped_column(Text)              # xDescServ (até 2000)
    ctribnac: Mapped[str] = mapped_column(String(6))           # código de tributação nacional (LC 116)
    cnbs: Mapped[str] = mapped_column(String(9))               # NBS 2.0
    ctribmun: Mapped[str | None] = mapped_column(String(10))   # código municipal (Sefin: 3 dígitos; ISSNet DF: até 10)
    cindop: Mapped[str | None] = mapped_column(String(6))      # IBS/CBS: indicador da operação
    cclasstrib: Mapped[str | None] = mapped_column(String(6))  # IBS/CBS: classificação tributária
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class Tomador(Base):
    """Tomador salvo do escritório, reaproveitado nas próximas notas."""
    __tablename__ = "tomador"
    __table_args__ = (UniqueConstraint("escritorio_id", "documento", name="uq_tomador_escritorio_documento"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    # CNPJ (14) ou CPF (11); no exterior, chave própria: EX + país + NIF (ou nome)
    documento: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(String(300))
    inscricao_municipal: Mapped[str | None] = mapped_column(String(15))
    cep: Mapped[str | None] = mapped_column(String(8))
    cod_municipio: Mapped[str | None] = mapped_column(String(7))  # IBGE
    municipio: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))
    logradouro: Mapped[str | None] = mapped_column(String(255))
    numero: Mapped[str | None] = mapped_column(String(60))
    complemento: Mapped[str | None] = mapped_column(String(156))
    bairro: Mapped[str | None] = mapped_column(String(60))
    telefone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(80))
    # Tomador no exterior
    pais: Mapped[str | None] = mapped_column(String(2))  # ISO 2 (nunca BR); vazio = Brasil
    nif: Mapped[str | None] = mapped_column(String(40))
    nao_nif: Mapped[str | None] = mapped_column(String(1))  # sem NIF: 1 dispensado | 2 não exigido
    cod_postal: Mapped[str | None] = mapped_column(String(11))
    cidade: Mapped[str | None] = mapped_column(String(60))
    estado_provincia: Mapped[str | None] = mapped_column(String(60))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


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
    """Pessoa do escritório. Nesta etapa não há papéis: vê todas as empresas do escritório."""
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    senha_hash: Mapped[str] = mapped_column(String(300))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False)
    # Administrador do sistema (suporte do Contask): cria escritórios e usuários pelo painel.
    # Só é concedido no servidor: python -m app.tools.usuarios admin EMAIL
    admin_sistema: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    ultimo_acesso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessaoUsuario(Base):
    """Sessão de login. Guarda só o SHA-256 do token do cookie."""
    __tablename__ = "sessao_usuario"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Monitoramento do uso (painel do administrador). Nada sai do servidor, e os textos das telas são
# mascarados no navegador antes de qualquer envio (frontend/src/lib/monitoramento.ts).
# ---------------------------------------------------------------------------

class UsoEvento(Base):
    """Evento de uso: pagina | tempo | clique | rolagem | erro | acao | login."""
    __tablename__ = "uso_evento"
    __table_args__ = (Index("ix_uso_evento_tipo_momento", "tipo", "momento"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    sessao: Mapped[str] = mapped_column(String(40), index=True)  # aba do navegador (id gerado lá)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    tipo: Mapped[str] = mapped_column(String(12))
    nome: Mapped[str] = mapped_column(String(120))  # rota normalizada (/empresas/:id) ou nome da ação
    dados: Mapped[dict | None] = mapped_column(JSON)


class Gravacao(Base):
    """Gravação da sessão (rrweb, com todo texto e campo mascarado). Apagada depois de 30 dias."""
    __tablename__ = "gravacao"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    sessao: Mapped[str] = mapped_column(String(40), unique=True)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    pagina_inicial: Mapped[str | None] = mapped_column(String(120))
    paginas: Mapped[list | None] = mapped_column(JSON)  # rotas visitadas, na ordem
    tamanho: Mapped[int] = mapped_column(Integer, default=0)  # bytes gravados (comprimidos)
    arquivo: Mapped[str] = mapped_column(String(300))  # relativo a dados/


class PesquisaResposta(Base):
    """Pesquisa no app: decepção (Sean Ellis), horas economizadas e NPS. adiada = respondo depois."""
    __tablename__ = "pesquisa_resposta"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    adiada: Mapped[bool] = mapped_column(Boolean, default=False)
    decepcao: Mapped[str | None] = mapped_column(String(10))  # muito | pouco | nada
    horas: Mapped[int | None] = mapped_column(Integer)  # horas economizadas por mês
    nps: Mapped[int | None] = mapped_column(Integer)  # 0 a 10
    comentario: Mapped[str | None] = mapped_column(Text)


class PedidoSuporte(Base):
    __tablename__ = "pedido_suporte"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    assunto: Mapped[str] = mapped_column(String(20))
    mensagem: Mapped[str] = mapped_column(Text)
    pagina: Mapped[str | None] = mapped_column(String(120))
    situacao: Mapped[str] = mapped_column(String(10), default="aberto")  # aberto | resolvido
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
