import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { EstadoErro, Esqueleto } from "@/components/estados";
import { api } from "./api";

/**
 * Sessão da administração: separada da sessão do sistema (login, cookie e duração próprios).
 * Estar logado no sistema não abre a administração, e vice-versa.
 */
export interface SessaoAdmin {
  /** trocar_senha: senha inicial, troca obrigatória antes de usar a administração */
  usuario: { id: number; email: string; nome: string; trocar_senha: boolean } | null;
}

/** Disparado pelo cliente da API quando uma rota /api/admin responde 401. */
export const EVENTO_SESSAO_ADMIN = "contask:sessao-admin";
export const CHAVE_SESSAO_ADMIN = ["sessao-admin"];

export function useSessaoAdmin() {
  return useQuery({ queryKey: CHAVE_SESSAO_ADMIN, queryFn: () => api<SessaoAdmin>("/api/admin/auth/eu"), staleTime: 5 * 60_000 });
}

/** Envolve as telas da administração: sem a sessão própria, vai para /admin/entrar. */
export function ProtegidoAdmin({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  useEffect(() => {
    const f = () => qc.invalidateQueries({ queryKey: CHAVE_SESSAO_ADMIN });
    window.addEventListener(EVENTO_SESSAO_ADMIN, f);
    return () => window.removeEventListener(EVENTO_SESSAO_ADMIN, f);
  }, [qc]);
  const { data, isLoading, isError, refetch } = useSessaoAdmin();
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
        <EstadoErro mensagem="Não foi possível confirmar a sessão da administração." tentarDeNovo={() => refetch()} />
      </div>
    );
  if (!data?.usuario) return <Navigate to="/admin/entrar" replace state={{ voltar: local.pathname + local.search }} />;
  return <>{children}</>;
}
