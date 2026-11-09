import { NavLink, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";

const ABAS = [
  { rota: "/emissor", rotulo: "Empresas emissoras", exato: false },
  { rota: "/emissor/tomadores", rotulo: "Tomadores", exato: true },
];

/** Abas da área do emissor de NFS-e. */
export function AbasEmissor() {
  const { pathname, search } = useLocation();
  return (
    <nav className="mb-6 flex gap-1 border-b border-borda" aria-label="Seções do emissor">
      {ABAS.map((a) => {
        const ativa = a.rota === "/emissor"
          ? pathname === "/emissor" || pathname.startsWith("/emissor/empresas")
          : pathname === a.rota;
        return (
          <NavLink key={a.rota} to={{ pathname: a.rota, search }} aria-current={ativa ? "page" : undefined}
            className={cn("-mb-px border-b-2 px-3 pb-2.5 text-sm transition-colors duration-150",
              ativa ? "border-destaque font-medium text-destaque" : "border-transparent text-texto-2 hover:text-texto")}>
            {a.rotulo}
          </NavLink>
        );
      })}
    </nav>
  );
}
