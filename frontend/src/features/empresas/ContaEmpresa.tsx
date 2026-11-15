import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { EstadoErro, Esqueleto } from "@/components/estados";
import { useContabilidade } from "@/lib/empresas";
import { useContaEmpresa, useSessao } from "@/lib/sessao";

/** Página inicial: o emissor na conta de empresa, o dashboard na de contador. */
export function Inicio() {
  const { data, isLoading } = useSessao();
  if (isLoading) return <Esqueleto className="h-64 w-full" />;
  return <Navigate to={data?.escritorio?.tipo === "empresa" ? "/emissor" : "/dashboard"} replace />;
}

/** "Minha empresa": o cadastro do único CNPJ da conta de empresa (ou o primeiro cadastro, se ainda não existe). */
export function MinhaEmpresa() {
  const { data, isLoading, isError, error, refetch } = useContabilidade();
  if (isLoading) return <Esqueleto className="h-96 w-full" />;
  if (isError) return <EstadoErro mensagem={(error as Error).message} tentarDeNovo={() => refetch()} />;
  return <Navigate to={data ? `/empresas/${data.id}?empresa=${data.id}` : "/contabilidade"} replace />;
}

/** Telas que cadastram ou listam várias empresas: na conta de empresa, vão para "Minha empresa". */
export function SoContador({ children }: { children: ReactNode }) {
  const sessao = useSessao();
  const contaEmpresa = useContaEmpresa();
  if (sessao.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (contaEmpresa) return <Navigate to="/minha-empresa" replace />;
  return <>{children}</>;
}
