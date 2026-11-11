import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { EstadoErro, Esqueleto } from "@/components/estados";
import { api } from "./api";

export interface Usuario {
  id: number;
  email: string;
  nome: string;
  trocar_senha: boolean;
}

export interface Sessao {
  usuario: Usuario | null;
  escritorio: { id: number; nome: string } | null;
  tem_contabilidade: boolean;
  empresas: number;
  /** só sem login: aberto (local) | convite | fechado (servidor: contas criadas pelo suporte) */
  cadastro?: "aberto" | "convite" | "fechado";
}

export interface Uso {
  mes: string;
  usados: number;
  limite: number | null;
  percentual: number | null;
  situacao: "sem_limite" | "ok" | "aviso" | "atingido" | "teste";
  teste: { max_xmls: number; max_empresas: number; concluido: boolean } | null;
}

/** Disparado pelo cliente da API quando o servidor responde 401/403 de sessão. */
export const EVENTO_SESSAO = "contask:sessao";

export function useSessao() {
  return useQuery({ queryKey: ["sessao"], queryFn: () => api<Sessao>("/api/auth/eu"), staleTime: 5 * 60_000 });
}

export function useUso(ativo = true) {
  return useQuery({ queryKey: ["uso"], queryFn: () => api<Uso>("/api/uso"), enabled: ativo, refetchInterval: 5 * 60_000 });
}

/** Reconsulta a sessão quando a API avisa que ela caiu (expirou, saiu em outra aba, troca de senha). */
function useOuvirSessao() {
  const qc = useQueryClient();
  useEffect(() => {
    const f = () => qc.invalidateQueries({ queryKey: ["sessao"] });
    window.addEventListener(EVENTO_SESSAO, f);
    return () => window.removeEventListener(EVENTO_SESSAO, f);
  }, [qc]);
}

/** Envolve as telas do sistema: sem sessão vai para /entrar; com troca pendente, para /trocar-senha. */
export function Protegido({ children }: { children: ReactNode }) {
  useOuvirSessao();
  const { data, isLoading, isError, refetch } = useSessao();
  const local = useLocation();
  if (isLoading)
    return (
      <div className="mx-auto max-w-sm px-6 py-24" aria-busy="true">
        <Esqueleto className="h-48 w-full" />
      </div>
    );
  if (isError)
    return (
      <div className="mx-auto max-w-sm px-6 py-24">
        <EstadoErro mensagem="Não foi possível confirmar a sessão." tentarDeNovo={() => refetch()} />
      </div>
    );
  if (!data?.usuario) return <Navigate to="/entrar" replace state={{ voltar: local.pathname + local.search }} />;
  if (data.usuario.trocar_senha) return <Navigate to="/trocar-senha" replace />;
  return <>{children}</>;
}
