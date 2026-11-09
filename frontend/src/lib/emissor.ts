import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type SituacaoCert } from "./api";

export interface ConfigPrestador {
  inscricao_municipal: string | null;
  op_simples: "1" | "2" | "3";
  reg_ap_trib_sn: "1" | "2" | "3" | null;
  reg_esp_trib: string;
  serie: string;
  proximo_numero: number;
  producao_liberada: boolean;
}

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
  atualizado_em?: string;
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
