import { FlaskConical } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useAmbienteEmissor } from "@/lib/emissor";
import { cn } from "@/lib/utils";

const ABAS = [
  { rota: "/emissor", rotulo: "Notas emitidas", ativa: (p: string) => p === "/emissor" },
  { rota: "/emissor/emitir", rotulo: "Emitir nota", ativa: (p: string) => p === "/emissor/emitir" },
  { rota: "/emissor/empresas", rotulo: "Empresas emissoras", ativa: (p: string) => p.startsWith("/emissor/empresas") },
  { rota: "/emissor/tomadores", rotulo: "Tomadores", ativa: (p: string) => p === "/emissor/tomadores" },
];

/** Faixa de homologação: notas sem valor fiscal enquanto a produção não for liberada. */
export function FaixaAmbiente() {
  const amb = useAmbienteEmissor();
  if (!amb.data || amb.data.producao) return null;
  return (
    <div role="status" className="mb-4 flex items-center gap-2 rounded-xl border border-rejeitada/30 bg-rejeitada-suave px-3.5 py-2 text-sm">
      <FlaskConical className="size-4 shrink-0 text-rejeitada" aria-hidden />
      <span><strong>Homologação.</strong> As notas vão para a produção restrita da Sefin e não têm valor fiscal.</span>
    </div>
  );
}

/** Abas da área do emissor de NFS-e. */
export function AbasEmissor() {
  const { pathname, search } = useLocation();
  return (
    <>
      <FaixaAmbiente />
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-borda" aria-label="Seções do emissor">
        {ABAS.map((a) => {
          const ativa = a.ativa(pathname);
          return (
            <NavLink key={a.rota} to={{ pathname: a.rota, search }} aria-current={ativa ? "page" : undefined} end
              className={cn("-mb-px whitespace-nowrap border-b-2 px-3 pb-2.5 text-sm transition-colors duration-150",
                ativa ? "border-destaque font-medium text-destaque" : "border-transparent text-texto-2 hover:text-texto")}>
              {a.rotulo}
            </NavLink>
          );
        })}
      </nav>
    </>
  );
}
