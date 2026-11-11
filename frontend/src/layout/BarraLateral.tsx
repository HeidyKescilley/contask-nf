import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { Dica } from "@/components/ui/tooltip";
import { useSessao } from "@/lib/sessao";
import { cn } from "@/lib/utils";
import { NAV_ADMIN, NAVEGACAO } from "./navegacao";

export function BarraLateral({ recolhida, alternar }: { recolhida: boolean; alternar: () => void }) {
  // Rota ativa calculada aqui: o Slot do tooltip não aceita className em forma de função.
  const { search, pathname } = useLocation();
  const admin = !!useSessao().data?.usuario?.admin_sistema;
  const itens = admin ? [...NAVEGACAO, NAV_ADMIN] : NAVEGACAO;
  return (
    <aside
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r border-borda bg-superficie transition-[width] duration-150",
        recolhida ? "w-[60px]" : "w-60",
      )}
      aria-label="Navegação principal"
    >
      <div className={cn("flex h-14 items-center gap-2.5 border-b border-borda", recolhida ? "justify-center" : "px-4")}>
        <img src="/icone.svg" alt="" className="size-7" />
        {!recolhida && (
          <span className="text-[15px] font-semibold tracking-tight">
            Contask <span className="text-destaque">NF</span>
          </span>
        )}
      </div>

      <nav className="flex-1 space-y-0.5 p-2">
        {itens.map(({ rota, rotulo, icone: Icone }) => {
          const ativa = pathname === rota || pathname.startsWith(`${rota}/`);
          return (
          <Dica key={rota} texto={rotulo} ativo={recolhida}>
            <NavLink
              to={{ pathname: rota, search }}
              aria-label={recolhida ? rotulo : undefined}
              className={cn(
                "flex h-9 items-center gap-3 rounded-lg text-sm transition-colors duration-150",
                recolhida ? "justify-center" : "px-3",
                ativa
                  ? "bg-destaque-suave font-medium text-destaque"
                  : "text-texto-2 hover:bg-superficie-2 hover:text-texto",
              )}
            >
              <Icone className="size-[18px] shrink-0" aria-hidden />
              {!recolhida && <span className="truncate">{rotulo}</span>}
            </NavLink>
          </Dica>
          );
        })}
      </nav>

      <div className="border-t border-borda p-2">
        <Dica texto="Expandir menu" ativo={recolhida}>
          <button
            onClick={alternar}
            aria-expanded={!recolhida}
            aria-label={recolhida ? "Expandir menu" : "Recolher menu"}
            className={cn(
              "flex h-9 w-full items-center gap-3 rounded-lg text-sm text-texto-2 hover:bg-superficie-2 hover:text-texto",
              recolhida ? "justify-center" : "px-3",
            )}
          >
            {recolhida ? <PanelLeftOpen className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
            {!recolhida && <span>Recolher menu</span>}
          </button>
        </Dica>
      </div>
    </aside>
  );
}
