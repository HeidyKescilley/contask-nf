import { FlaskConical } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useEmpresasEmissoras } from "@/lib/emissor";
import { useEmpresaSelecionada } from "@/lib/empresas";
import { cn } from "@/lib/utils";

const ABAS = [
  { rota: "/emissor", rotulo: "Notas", ativa: (p: string) => p === "/emissor" },
  { rota: "/emissor/emitir", rotulo: "Emitir nota", ativa: (p: string) => p === "/emissor/emitir" },
  { rota: "/emissor/recorrentes", rotulo: "Recorrentes", ativa: (p: string) => p.startsWith("/emissor/recorrentes") },
  { rota: "/emissor/empresas", rotulo: "Empresas emissoras", ativa: (p: string) => p.startsWith("/emissor/empresas") },
  { rota: "/emissor/tomadores", rotulo: "Tomadores", ativa: (p: string) => p === "/emissor/tomadores" },
];

/** Aviso de homologação: só aparece quando a empresa selecionada emite na homologação. */
export function FaixaAmbiente({ empresaId }: { empresaId?: number | null }) {
  const { empresa: selecionada } = useEmpresaSelecionada();
  const empresas = useEmpresasEmissoras();
  const id = empresaId ?? selecionada?.id;
  const e = empresas.data?.find((x) => x.id === id);
  if (!e || !e.emite_nfse || e.ambiente !== 2) return null;
  return (
    <div role="status" className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-rejeitada/30 bg-rejeitada-suave px-3.5 py-2 text-sm">
      <FlaskConical className="size-4 shrink-0 text-rejeitada" aria-hidden />
      <span><strong>Homologação.</strong> As notas desta empresa vão para a produção restrita da Sefin e não têm valor fiscal.</span>
      <Link to={`/emissor/empresas/${e.id}?empresa=${e.id}`} className="font-medium text-destaque hover:underline">Mudar o ambiente</Link>
    </div>
  );
}

/** Abas da área do emissor de NFS-e. */
export function AbasEmissor({ empresaId }: { empresaId?: number | null }) {
  const { pathname, search } = useLocation();
  // Só a empresa selecionada segue entre as abas; filtros e ids de uma página não vão para a outra
  const empresa = new URLSearchParams(search).get("empresa");
  const busca = empresa ? `?empresa=${empresa}` : "";
  return (
    <>
      <FaixaAmbiente empresaId={empresaId} />
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-borda" aria-label="Seções do emissor">
        {ABAS.map((a) => {
          const ativa = a.ativa(pathname);
          return (
            <NavLink key={a.rota} to={{ pathname: a.rota, search: busca }} aria-current={ativa ? "page" : undefined} end
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
