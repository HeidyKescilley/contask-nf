import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, apiArquivo, ErroApi, type SituacaoCert } from "./api";

export interface ConfigPrestador {
  inscricao_municipal: string | null;
  op_simples: "1" | "2" | "3";
  reg_ap_trib_sn: "1" | "2" | "3" | null;
  reg_esp_trib: string;
  serie: string;
  proximo_numero: number;
  /** IBGE do município (7 dígitos), descoberto sozinho pelo município e UF da empresa */
  cod_municipio: string | null;
  producao_liberada: boolean;
  regime_tributario: RegimeTributario | null;
  /** true quando a empresa é do Simples (regime escolhido ou, sem ele, MEI/ME-EPP): acrescenta o texto legal */
  simples: boolean;
  /** fora do Simples (regime regular): a nota leva o grupo IBS/CBS, e o serviço precisa do cIndOp e do cClassTrib */
  exige_ibscbs?: boolean;
  /** texto fixo das informações complementares (dados bancários, observações), em toda nota da empresa */
  texto_fixo?: string | null;
}

export type RegimeTributario = "simples" | "presumido" | "real";

export const REGIMES: Record<RegimeTributario, string> = {
  simples: "Simples Nacional",
  presumido: "Lucro Presumido",
  real: "Lucro Real",
};

export const TEXTO_SIMPLES = 'I - "DOCUMENTO EMITIDO POR ME OU EPP OPTANTE PELO SIMPLES NACIONAL"; e II - "NÃO GERA DIREITO A CRÉDITO FISCAL DE IPI."';
export const TEXTO_PROCON = "PROCON: TEL 151- SETOR COMERCIAL SUL, QUADRA 8, BLOCO B-60, SALA 240- BRASILIA - DF";

export interface EmpresaEmissora {
  id: number;
  cnpj: string;
  razao_social: string;
  nome_fantasia: string | null;
  apelido: string | null;
  uf: string | null;
  municipio: string | null;
  ativa: boolean;
  is_contabilidade: boolean;
  emite_nfse: boolean;
  certificado: { titular_nome: string; titular_doc: string; validade: string; situacao: SituacaoCert; filial: boolean; procuracao: boolean } | null;
  servicos: number;
  config: ConfigPrestador | null;
  pendencias: string[];
  pronta: boolean;
  avisos: string[];
  /** 1 = produção (valor fiscal), 2 = produção restrita (homologação) */
  ambiente: 1 | 2;
  /** Por onde a nota sai: Sefin Nacional ou, para empresa do DF fora do Simples, o ISSNet do DF */
  canal: CanalEmissao;
}

export type CanalEmissao = "nacional" | "issnet_df";

/** cTribMun do DF (tabela de correlação do ISSNet) */
export interface CodigoMunicipalDf { codigo: string; descricao: string; aliquota: string | null; ctribnac: string[] }

/** Monitoramento dos RPS liberados no ISSNet do DF */
export interface ResumoRps {
  disponiveis: number;
  reservados: number;
  usados_fora: number;
  consumo_30_dias: number;
  limite_alerta: number;
  nivel: "ok" | "baixo" | "zerado" | "sem_dados";
  faixas: { serie: string; de: number; ate: number; quantidade: number }[];
  sincronizado_em: string | null;
  erro: string | null;
}

export function useRps(empresaId: number, ativo = true) {
  return useQuery({
    enabled: ativo,
    queryKey: ["emissor", "rps", empresaId],
    queryFn: () => api<ResumoRps>(`/api/emissor/empresas/${empresaId}/rps`),
  });
}

export interface Servico {
  id: number;
  empresa_id: number;
  descricao: string;
  ctribnac: string;
  ctribnac_formatado: string;
  ctribnac_descricao: string | null;
  cnbs: string;
  cnbs_formatado: string;
  cnbs_descricao: string | null;
  ctribmun: string | null;
  cindop: string | null;
  cclasstrib: string | null;
  ativo: boolean;
  atualizado_em: string;
}

export interface CodigoServico { codigo: string; codigo_formatado: string; item: string; descricao: string }
export interface CodigoNbs { codigo: string; codigo_formatado: string; descricao: string }
export interface OpcaoCIndOp {
  codigo: string; tipo: string; caracteristica: string; local: string; incidencia: string;
  sugerido: boolean; exige_endereco_tomador: boolean;
}
export interface OpcaoCClassTrib {
  codigo: string; cst: string; nome_cst: string; nome: string; red_ibs: number; red_cbs: number; lei: string | null; sugerido: boolean;
}
export interface OpcoesIbsCbs { cindop: OpcaoCIndOp[]; cclasstrib: OpcaoCClassTrib[] }

/** cIndOp e cClassTrib que valem para a NFS-e da empresa, com os sugeridos para o serviço (Anexo VIII) primeiro. */
export function useOpcoesIbsCbs(ctribnac?: string | null, cnbs?: string | null) {
  return useQuery({
    queryKey: ["emissor", "ibscbs", ctribnac ?? "", cnbs ?? ""],
    queryFn: () => api<OpcoesIbsCbs>(`/api/emissor/codigos/ibscbs?${new URLSearchParams({ ctribnac: ctribnac ?? "", cnbs: cnbs ?? "" })}`),
    staleTime: Infinity,
  });
}

export interface Sugestao { nbs: string; nbs_formatado: string; nbs_descricao: string | null; cindop: string | null; cclasstrib: string | null }

export interface Tomador {
  id?: number;
  documento: string;
  nome: string;
  inscricao_municipal?: string | null;
  cep?: string | null;
  cod_municipio?: string | null;
  municipio?: string | null;
  uf?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  telefone?: string | null;
  email?: string | null;
  /** tomador no exterior: país ISO 2 (vazio/BR = Brasil), NIF ou motivo de não ter (1/2) e endereço */
  pais?: string | null;
  nif?: string | null;
  nao_nif?: string | null;
  cod_postal?: string | null;
  cidade?: string | null;
  estado_provincia?: string | null;
  atualizado_em?: string;
}

/** Grupo comExt da nota com tomador no exterior (ver api.emissor.ComercioExteriorIn). */
export interface ComercioExterior {
  moeda: string; valor_moeda: string | number; exportacao: boolean; modo: string; vinculo: string;
  mec_prestador: string; mec_tomador: string; mov_temp_bens: string; mdic: string;
}

export interface ConsultaTomador {
  origem: "salvo" | "brasilapi" | "manual";
  tomador: Partial<Tomador> & { documento: string };
  aviso: string | null;
}

export const OP_SIMPLES: Record<string, string> = {
  "1": "Não optante pelo Simples Nacional",
  "2": "MEI",
  "3": "ME/EPP optante pelo Simples Nacional",
};

export const REG_AP_TRIB_SN: Record<string, string> = {
  "1": "Tributos federais e municipal pelo Simples",
  "2": "Federais pelo Simples, ISS fora do Simples",
  "3": "Federais e municipal fora do Simples",
};

export const REG_ESP_TRIB: Record<string, string> = {
  "0": "Nenhum",
  "1": "Ato cooperado (cooperativa)",
  "2": "Estimativa",
  "3": "Microempresa municipal",
  "4": "Notário ou registrador",
  "5": "Profissional autônomo",
  "6": "Sociedade de profissionais",
  "9": "Outros",
};

export function useEmpresasEmissoras() {
  return useQuery({ queryKey: ["emissor", "empresas"], queryFn: () => api<EmpresaEmissora[]>("/api/emissor/empresas") });
}

export function useEmpresaEmissora(id: number) {
  return useQuery({ queryKey: ["emissor", "empresa", id], queryFn: () => api<EmpresaEmissora>(`/api/emissor/empresas/${id}`) });
}

/** Códigos do serviço levados na própria nota (duplicar sem ter o serviço cadastrado). */
export interface CodigosServico {
  ctribnac: string;
  cnbs: string;
  ctribmun: string | null;
  cindop: string | null;
  cclasstrib: string | null;
  ctribnac_formatado?: string | null;
  ctribnac_descricao?: string | null;
  cnbs_formatado?: string | null;
  cnbs_descricao?: string | null;
}

export const codigosIguais = (a: { [K in keyof CodigosServico]?: CodigosServico[K] | null }, b: { [K in keyof CodigosServico]?: CodigosServico[K] | null }) =>
  (["ctribnac", "cnbs", "ctribmun", "cindop", "cclasstrib"] as const).every((k) => (a[k] || null) === (b[k] || null));

/** Última NFS-e prestada que veio do ADN: dados do prestador e do serviço para pré-preencher o emissor. */
export interface UltimaNota {
  nota_id: number;
  numero_nfse: string | null;
  data: string | null;
  chave: string | null;
  emitida_pelo_contask: boolean;
  prestador: {
    inscricao_municipal: string | null;
    op_simples: "1" | "2" | "3" | null;
    reg_ap_trib_sn: string | null;
    reg_esp_trib: string | null;
    cod_municipio: string | null;
    serie: string | null;
    numero_dps: number | null;
  };
  servico: (CodigosServico & { descricao: string }) | null;
  servico_cadastrado: boolean;
}

export function useUltimaNota(empresaId: number) {
  return useQuery({
    queryKey: ["emissor", "ultima-nota", empresaId],
    queryFn: () => api<UltimaNota | null>(`/api/emissor/empresas/${empresaId}/ultima-nota`),
    staleTime: 60_000,
  });
}

export function useServicos(empresaId: number, inativos = false) {
  return useQuery({
    queryKey: ["emissor", "servicos", empresaId, inativos],
    queryFn: () => api<Servico[]>(`/api/emissor/empresas/${empresaId}/servicos${inativos ? "?inativos=true" : ""}`),
  });
}

/** Invalida tudo do emissor e o cadastro de empresas (que mostra a opção "Emite NFS-e"). */
export function useAtualizarEmissor() {
  const qc = useQueryClient();
  return useCallback(() => {
    qc.invalidateQueries({ queryKey: ["emissor"] });
    qc.invalidateQueries({ queryKey: ["empresas"] });
    qc.invalidateQueries({ queryKey: ["empresa"] });
  }, [qc]);
}

export function apenasDigitos(v: string | null | undefined) {
  return (v ?? "").replace(/\D/g, "");
}

export function mascararCep(v: string | null | undefined) {
  const d = apenasDigitos(v).slice(0, 8);
  return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
}

export type SituacaoEmitida = "enviando" | "autorizada" | "rejeitada" | "pendente" | "cancelada";

export interface ErroSefin { codigo: string | null; descricao: string | null; complemento: string | null }

export interface NotaEmitida {
  comercio_exterior?: ComercioExterior | null;
  id: number;
  empresa_id: number;
  empresa_nome: string;
  empresa_cnpj: string;
  servico_id: number | null;
  ambiente: 1 | 2;
  homologacao: boolean;
  serie: string;
  numero: number;
  id_dps: string;
  situacao: SituacaoEmitida;
  competencia: string;
  tomador: Tomador | null;
  descricao: string;
  ctribnac: string;
  ctribnac_formatado: string;
  cnbs: string;
  cnbs_formatado: string;
  ctribmun: string | null;
  cindop: string | null;
  cclasstrib: string | null;
  canal?: CanalEmissao;
  cod_municipio_prestacao: string;
  valor_servico: number;
  desconto: number;
  iss_retido: boolean;
  aliquota_iss: number | null;
  ret_pis: number;
  ret_cofins: number;
  ret_csll: number;
  ret_irrf: number;
  ret_cp: number;
  info_complementar: string | null;
  chave: string | null;
  numero_nfse: string | null;
  valor_iss: number | null;
  valor_liquido: number | null;
  erros: ErroSefin[];
  mensagem: string | null;
  motivo_cancelamento: string | null;
  criado_em: string;
  enviado_em: string | null;
  autorizado_em: string | null;
  cancelado_em: string | null;
  /** false quando a empresa emite por procuração: a Sefin recusa o cancelamento (E0812/E0813) */
  cancela_pela_api: boolean;
  origem: "contask";
  data: string;
  recorrente_id: number | null;
  /** informações complementares sem os textos legais, que vêm marcados abaixo */
  info_usuario: string;
  texto_simples: boolean;
  texto_procon: boolean;
  texto_fixo?: boolean;
  /** substituição: chave da NFS-e que esta substitui e a ligação com a outra nota do Contask */
  subst_chave: string | null;
  subst_motivo: string | null;
  subst_justificativa: string | null;
  substitui: RefNota | null;
  substituida_por: RefNota | null;
}

export interface RefNota { id: number; numero_nfse: string | null; situacao: SituacaoEmitida }

/** Códigos de justificativa da substituição (TSCodJustSubst do leiaute da NFS-e). */
export const MOTIVOS_SUBSTITUICAO = [
  { codigo: "99", rotulo: "Outros (erro de preenchimento, tomador, valor, descrição…)" },
  { codigo: "05", rotulo: "Rejeição da NFS-e pelo tomador ou intermediário" },
  { codigo: "01", rotulo: "Desenquadramento de NFS-e do Simples Nacional" },
  { codigo: "02", rotulo: "Enquadramento de NFS-e no Simples Nacional" },
  { codigo: "03", rotulo: "Inclusão retroativa de imunidade/isenção" },
  { codigo: "04", rotulo: "Exclusão retroativa de imunidade/isenção" },
] as const;

/** Nota prestada que veio do ADN (emitida fora do Contask). */
export interface NotaAdn {
  origem: "adn";
  id: number;
  empresa_id: number;
  data: string | null;
  chave: string;
  numero_nfse: string | null;
  serie: string | null;
  numero: number | null;
  competencia: string | null;
  tomador: { documento: string | null; nome: string | null } | null;
  valor_servico: number | null;
  valor_liquido: number | null;
  situacao: "autorizada" | "cancelada" | "rejeitada";
  homologacao: false;
  descricao: null;
  mensagem: string | null;
  tem_xml: boolean;
}

export type ItemNota = NotaEmitida | NotaAdn;

export interface ListaNotas {
  ambiente: 1 | 2;
  notas: ItemNota[];
  totais: { quantidade: number; autorizadas: number; valor_autorizado: number };
}

export interface FiltrosNotas { inicio: string; fim: string; q: string; numero: string; situacao: string }

export function useNotasEmpresa(empresaId: number | null, f: FiltrosNotas) {
  const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][]);
  return useQuery({
    enabled: !!empresaId,
    queryKey: ["emissor", "notas-empresa", empresaId, f],
    queryFn: () => api<ListaNotas>(`/api/emissor/empresas/${empresaId}/notas?${p}`),
    placeholderData: (ant) => ant,
  });
}

/** Corpo da emissão (POST /api/emissor/notas). Rascunhos e recorrências guardam o mesmo formato. */
export interface CorpoEmissao {
  servico_id?: number | null;
  /** sem serviço cadastrado: os códigos vêm da nota duplicada */
  servico?: CodigosServico | null;
  /** tomador no exterior */
  comercio_exterior?: ComercioExterior | null;
  /** IBS/CBS desta nota (em branco: os do serviço) */
  cindop?: string | null;
  cclasstrib?: string | null;
  cod_municipio_prestacao?: string | null;
  descricao?: string;
  competencia?: string;
  valor?: string;
  desconto?: string;
  tomador?: Tomador | null;
  salvar_tomador?: boolean;
  iss_retido?: boolean;
  aliquota_iss?: string | null;
  ret_pis?: string; ret_cofins?: string; ret_csll?: string; ret_irrf?: string; ret_cp?: string;
  info_complementar?: string | null;
  texto_simples?: boolean;
  texto_procon?: boolean;
  texto_fixo?: boolean;
}

export interface Rascunho {
  id: number;
  empresa_id: number;
  dados: CorpoEmissao;
  tomador_nome: string | null;
  tomador_documento: string | null;
  valor: string | null;
  descricao: string;
  criado_em: string;
  atualizado_em: string;
}

export function useRascunhos(empresaId: number | null) {
  return useQuery({
    enabled: !!empresaId,
    queryKey: ["emissor", "rascunhos", empresaId],
    queryFn: () => api<Rascunho[]>(`/api/emissor/empresas/${empresaId}/rascunhos`),
  });
}

export interface Recorrente {
  id: number;
  empresa_id: number;
  nome: string;
  dia: number;
  competencia: "atual" | "anterior";
  ativa: boolean;
  dados: CorpoEmissao;
  proxima_em: string | null;
  ultima_em: string | null;
  ultimo_erro: string | null;
  tomador_nome: string | null;
  tomador_documento: string | null;
  valor: string | null;
  previa: { data: string; competencia: string; descricao: string } | null;
  ultima_nota: { id: number; numero_nfse: string | null; situacao: SituacaoEmitida; mensagem: string | null } | null;
  criado_em: string;
}

export function useRecorrentes(empresaId: number | null) {
  return useQuery({
    enabled: !!empresaId,
    queryKey: ["emissor", "recorrentes", empresaId],
    queryFn: () => api<Recorrente[]>(`/api/emissor/empresas/${empresaId}/recorrentes`),
  });
}

/** Modelo para duplicar uma nota do ADN (lida do XML). */
export interface ModeloAdn {
  comercio_exterior?: ComercioExterior | null;
  empresa_id: number;
  numero_nfse: string | null;
  competencia?: string | null;
  chave?: string | null;
  situacao?: string;
  servico_id: number | null;
  ctribnac: string | null;
  cnbs: string | null;
  ctribmun: string | null;
  cindop: string | null;
  cclasstrib: string | null;
  ctribnac_formatado: string | null;
  ctribnac_descricao: string | null;
  cnbs_formatado: string | null;
  cnbs_descricao: string | null;
  cod_municipio_prestacao: string | null;
  descricao: string;
  tomador: Tomador | null;
  valor_servico: number;
  desconto: number;
  iss_retido: boolean;
  aliquota_iss: number | null;
  ret_pis: number; ret_cofins: number; ret_csll: number; ret_irrf: number; ret_cp: number;
  info_usuario: string;
  texto_simples: boolean;
  texto_procon: boolean;
  texto_fixo?: boolean;
}

// ---------------------------------------------------------------------------
// Variáveis das notas recorrentes (mesma regra do backend: app/emissor/textos.py)
// ---------------------------------------------------------------------------

export const VARIAVEIS: { nome: string; descricao: string }[] = [
  { nome: "mes_anterior", descricao: "Mês anterior (MM/AAAA)" },
  { nome: "mes_atual", descricao: "Mês da emissão (MM/AAAA)" },
  { nome: "primeiro_dia_mes_anterior", descricao: "1º dia do mês anterior" },
  { nome: "ultimo_dia_mes_anterior", descricao: "Último dia do mês anterior" },
  { nome: "primeiro_dia_mes_atual", descricao: "1º dia do mês da emissão" },
  { nome: "ultimo_dia_mes_atual", descricao: "Último dia do mês da emissão" },
];

const p2 = (n: number) => String(n).padStart(2, "0");
const ultimoDia = (a: number, m: number) => new Date(a, m, 0).getDate(); // m de 1 a 12

export function valoresVariaveis(emissao: Date): Record<string, string> {
  const a = emissao.getFullYear(), m = emissao.getMonth() + 1;
  const [aa, ma] = m === 1 ? [a - 1, 12] : [a, m - 1];
  return {
    mes_atual: `${p2(m)}/${a}`, mes_anterior: `${p2(ma)}/${aa}`,
    primeiro_dia_mes_atual: `01/${p2(m)}/${a}`, ultimo_dia_mes_atual: `${ultimoDia(a, m)}/${p2(m)}/${a}`,
    primeiro_dia_mes_anterior: `01/${p2(ma)}/${aa}`, ultimo_dia_mes_anterior: `${ultimoDia(aa, ma)}/${p2(ma)}/${aa}`,
  };
}

export function aplicarVariaveis(texto: string, emissao: Date) {
  const v = valoresVariaveis(emissao);
  return texto.replace(/\{([^{}]*)\}/g, (todo, nome: string) => v[nome.trim()] ?? todo);
}

export function variaveisDesconhecidas(texto: string) {
  const nomes = new Set(VARIAVEIS.map((v) => v.nome));
  return [...new Set([...texto.matchAll(/\{([^{}]*)\}/g)].map((m) => m[1].trim()).filter((n) => !nomes.has(n)))];
}

/** Próxima data (estritamente futura) do dia escolhido; meses curtos usam o último dia. */
export function proximaData(dia: number, hoje = new Date()): Date {
  const h = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  const noMes = (a: number, m0: number) => new Date(a, m0, Math.min(dia, ultimoDia(a, m0 + 1)));
  const d = noMes(h.getFullYear(), h.getMonth());
  return d > h ? d : noMes(h.getMonth() === 11 ? h.getFullYear() + 1 : h.getFullYear(), (h.getMonth() + 1) % 12);
}

/** Chave geral: com ela ligada, cada empresa ainda precisa ser liberada para a produção. */
export interface AmbienteEmissor { producao_disponivel: boolean; ambiente: 1 | 2; producao: boolean; descricao: string }

export function useAmbienteEmissor() {
  return useQuery({ queryKey: ["emissor", "ambiente"], queryFn: () => api<AmbienteEmissor>("/api/emissor/ambiente"), staleTime: Infinity });
}

export function useNotasEmitidas(filtros: { empresa_id?: number | null; situacao?: string | null; ambiente?: 1 | 2 | null }, ativa = true) {
  const p = new URLSearchParams();
  if (filtros.empresa_id) p.set("empresa_id", String(filtros.empresa_id));
  if (filtros.situacao) p.set("situacao", filtros.situacao);
  if (filtros.ambiente) p.set("ambiente", String(filtros.ambiente));
  return useQuery({
    enabled: ativa,
    queryKey: ["emissor", "notas", filtros],
    queryFn: () => api<NotaEmitida[]>(`/api/emissor/notas?${p}`),
    placeholderData: (ant) => ant,
  });
}

/** "1.234,56" ou "1234.56" -> 1234.56 (NaN se vazio/ inválido). */
export function lerValor(v: string): number {
  const s = (v ?? "").trim();
  if (!s) return NaN;
  const milhar = /^\d{1,3}(\.\d{3})+$/.test(s); // "1.500" = mil e quinhentos
  const normal = s.includes(",") || milhar ? s.replace(/\./g, "").replace(",", ".") : s;
  return /^\d+(\.\d{0,2})?$/.test(normal) ? Number(normal) : NaN;
}

export function escreverValor(n: number | null | undefined): string {
  if (n === null || n === undefined || isNaN(n)) return "";
  return n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export const arredondar = (n: number) => Math.round(n * 100) / 100;

/** Prévia da nota (PDF no leiaute do DANFSe, sem valor fiscal). A aba é aberta já no clique, antes da
 *  resposta, senão o navegador bloqueia como pop-up; sem aba (bloqueada mesmo assim), o PDF é baixado. */
export async function abrirPrevia(corpo: CorpoEmissao & { empresa_id: number }): Promise<void> {
  const aba = window.open("", "_blank");
  if (aba) aba.document.title = "Gerando a prévia…";
  try {
    const pdf = await apiArquivo("/api/emissor/notas/previa", corpo);
    const url = URL.createObjectURL(pdf);
    if (aba && !aba.closed) aba.location.href = url;
    else {
      const a = document.createElement("a");
      a.href = url;
      a.download = "Previa_NFS-e_sem_valor_fiscal.pdf";
      a.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    aba?.close();
    // 422 da validação de campos (sem mensagem própria): falta algo obrigatório no formulário
    if (e instanceof ErroApi && e.status === 422 && e.message === "Erro 422")
      throw new ErroApi(422, "Preencha o serviço, a competência e o valor para gerar a prévia.");
    throw e;
  }
}
