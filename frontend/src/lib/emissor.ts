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
  certificado: { titular_nome: string; titular_doc: string; validade: string; situacao: SituacaoCert; filial: boolean } | null;
  servicos: number;
  config: ConfigPrestador | null;
  pendencias: string[];
  pronta: boolean;
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
