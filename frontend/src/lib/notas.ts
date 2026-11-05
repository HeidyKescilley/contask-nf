import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "./api";

export type StatusNota = "autorizada" | "cancelada" | "rejeitada";
export type Papel = "prestada" | "tomada";

export interface Nota {
  id: number;
  chave: string;
  papel: string;
  numero: string | null;
  serie: string | null;
  emitente_doc: string | null;
  emitente_nome: string | null;
  emitente_uf: string | null;
  prestador_doc: string | null;
  tomador_doc: string | null;
  tomador_nome: string | null;
  valor_servico: number | null;
  valor_liquido: number | null;
  valor_iss: number | null;
  data_emissao: string | null;
  competencia: string | null;
  municipio: string | null;
  status: StatusNota;
  status_detalhe: string | null;
  em_analise_fiscal: boolean;
  bloqueada: boolean;
}

export interface DetalheNota extends Nota {
  n_dps: string | null;
  c_stat: string | null;
  nsu: number | null;
  empresa_id: number;
  eventos: { codigo: string | null; descricao: string; conhecido: boolean; data_evento: string | null; nsu: number | null }[];
}

export interface ListaNotas {
  itens: Nota[];
  total: number;
  pagina: number;
  limite: number;
  paginas: number;
  totais: { valor_autorizado: number; autorizadas: number; canceladas: number; rejeitadas: number };
}

export interface FiltrosNotas {
  q?: string;
  inicio?: string;
  fim?: string;
  campo_data?: "emissao" | "competencia";
  status?: string;
  page?: number;
  ordem?: string;
}

export function useNotas(empresaId: number | undefined, papel: Papel, f: FiltrosNotas) {
  const params = new URLSearchParams({ papel, limite: "50" });
  for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== "" && v !== null) params.set(k, String(v));
  return useQuery({
    queryKey: ["notas", empresaId, params.toString()],
    queryFn: () => api<ListaNotas>(`/api/empresas/${empresaId}/notas?${params}`),
    enabled: !!empresaId,
    placeholderData: keepPreviousData,
  });
}

export function useDetalheNota(id: number | null) {
  return useQuery({ queryKey: ["nota", id], queryFn: () => api<DetalheNota>(`/api/notas/${id}`), enabled: id !== null });
}

const fmtMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
export const moeda = (v: number | null | undefined) => (v === null || v === undefined ? "—" : fmtMoeda.format(v));

/** Data/hora de emissão como está no XML (sem converter fuso). */
export function dataHoraXml(iso: string | null) {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}` : iso;
}

export function dataXml(iso: string | null) {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

/** Atalhos de período (datas locais AAAA-MM-DD). */
export function periodo(atalho: "mes" | "mes_passado" | "trimestre" | "ano"): [string, string] {
  const hoje = new Date();
  const f = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const y = hoje.getFullYear(), m = hoje.getMonth();
  if (atalho === "mes") return [f(new Date(y, m, 1)), f(new Date(y, m + 1, 0))];
  if (atalho === "mes_passado") return [f(new Date(y, m - 1, 1)), f(new Date(y, m, 0))];
  if (atalho === "trimestre") {
    const t = Math.floor(m / 3) * 3;
    return [f(new Date(y, t, 1)), f(new Date(y, t + 3, 0))];
  }
  return [f(new Date(y, 0, 1)), f(new Date(y, 11, 31))];
}
