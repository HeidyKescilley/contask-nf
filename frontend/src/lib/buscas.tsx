import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";

export type StatusJob = "fila" | "rodando" | "pausado" | "concluido" | "erro" | "cancelado";

export interface Job {
  id: number;
  tipo: "inicial" | "incremental" | "refazer";
  status: StatusJob;
  empresa_id: number;
  empresa: { razao_social: string; apelido: string | null; nome_fantasia: string | null; cnpj: string } | null;
  situacao_empresa: string | null;
  tipo_consulta: string | null;
  certificado: { titular_nome: string; id: number } | null;
  modo_certificado: string | null;
  iniciado_em: string | null;
  finalizado_em: string | null;
  criado_em: string;
  duracao_s: number | null;
  paginas: number;
  docs_recebidos: number;
  notas_ok: number;
  eventos_ok: number;
  docs_com_erro: number;
  eventos_sem_nota: number;
  ultimo_nsu: number | null;
  mensagem: string | null;
  docs_por_min: number | null;
}

export interface EstadoBuscas {
  ativas: Job[];
  recentes: Job[];
  rodando: number;
  na_fila: number;
  fila_ativa: boolean;
}

export interface LinhaLog {
  momento: string;
  nivel: "info" | "aviso" | "erro";
  mensagem: string;
}

export function useBuscas() {
  return useQuery({ queryKey: ["buscas"], queryFn: () => api<EstadoBuscas>("/api/buscas"), refetchInterval: 30_000 });
}

export function useLogBusca(id: number, ativo: boolean) {
  return useQuery({ queryKey: ["buscas", "log", id], queryFn: () => api<LinhaLog[]>(`/api/buscas/${id}/log`), enabled: ativo });
}

export async function acaoBusca(id: number, acao: "pausar" | "retomar" | "cancelar") {
  return api<Job>(`/api/buscas/${id}/${acao}`, { method: "POST" });
}

export async function novaBusca(empresaId: number, tipo: "incremental" | "refazer") {
  return api<Job>(`/api/empresas/${empresaId}/buscas`, { method: "POST", body: JSON.stringify({ tipo }) });
}

/** Ouve o SSE e atualiza os caches (com limite de frequência). */
export function useEventosTempoReal() {
  const qc = useQueryClient();
  const pendente = useRef<number | null>(null);
  const terminais = useRef(false);
  useEffect(() => {
    const fonte = new EventSource("/api/eventos/stream");
    const agendar = () => {
      if (pendente.current !== null) return;
      pendente.current = window.setTimeout(() => {
        pendente.current = null;
        qc.invalidateQueries({ queryKey: ["buscas"] });
        qc.invalidateQueries({ queryKey: ["notas"] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["exportacoes"] });
        if (terminais.current) {
          terminais.current = false;
          qc.invalidateQueries({ queryKey: ["empresas"] });
          qc.invalidateQueries({ queryKey: ["empresa"] });
        }
      }, 700);
    };
    fonte.onmessage = (m) => {
      try {
        const ev = JSON.parse(m.data);
        if (ev.tipo === "job" && ev.status !== "rodando") terminais.current = true;
        if (ev.tipo === "job" && ev.status === "rodando" && ev.paginas === 0) terminais.current = true;
      } catch {
        /* ignora */
      }
      agendar();
    };
    return () => {
      fonte.close();
      if (pendente.current !== null) clearTimeout(pendente.current);
    };
  }, [qc]);
}

const CentralCtx = createContext<{ aberta: boolean; abrir: (empresaId?: number) => void; fechar: () => void; foco: number | null } | null>(null);

export function CentralProvider({ children }: { children: ReactNode }) {
  const [aberta, setAberta] = useState(false);
  const [foco, setFoco] = useState<number | null>(null);
  return (
    <CentralCtx.Provider value={{ aberta, foco, abrir: (id) => { setFoco(id ?? null); setAberta(true); }, fechar: () => setAberta(false) }}>
      {children}
    </CentralCtx.Provider>
  );
}

export function useCentral() {
  const c = useContext(CentralCtx);
  if (!c) throw new Error("useCentral fora do CentralProvider");
  return c;
}

export function rotuloAcesso(tipo: string | null | undefined, modo?: string | null) {
  if (tipo === "Procuracao") return "Procuração";
  if (tipo === "CnpjBase") return "Mesma raiz de CNPJ";
  if (tipo === "InscricaoCertificado") return "Certificado próprio";
  return modo === "contabilidade" ? "Procuração (a confirmar)" : modo === "proprio" ? "Certificado próprio" : "—";
}
