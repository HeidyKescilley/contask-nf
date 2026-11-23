import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { Dica } from "@/components/ui/tooltip";
import { useContaEmpresa, useSessao } from "@/lib/sessao";
import { cn, useCelular } from "@/lib/utils";
import { NAV_ADMIN, NAV_LEADS, NAV_MONITORAMENTO, NAVEGACAO, NAVEGACAO_EMPRESA } from "./navegacao";

export function BarraLateral({ recolhida: recolhidaDesktop, alternar, aberta, fechar }: {
  recolhida: boolean; alternar: () => void; aberta: boolean; fechar: () => void;
}) {
  // No celular o menu é uma gaveta (sempre com os nomes); no computador, recolhe para os ícones
  const celular = useCelular();
  const recolhida = recolhidaDesktop && !celular;
  // Rota ativa calculada aqui: o Slot do tooltip não aceita className em forma de função.
  const { search, pathname } = useLocation();
  const admin = !!useSessao().data?.usuario?.admin_sistema;
  const base = useContaEmpresa() ? NAVEGACAO_EMPRESA : NAVEGACAO;
  const itens = admin ? [...base, NAV_ADMIN, NAV_LEADS, NAV_MONITORAMENTO] : base;
  return (
    <>
    {celular && aberta && <div className="fixed inset-0 z-40 bg-black/40" onClick={fechar} aria-hidden />}
    <aside
      className={cn(
        "flex h-dvh shrink-0 flex-col border-r border-borda bg-superficie",
        celular
          ? cn("fixed inset-y-0 left-0 z-50 w-[min(16rem,85vw)] transition-transform duration-200", aberta ? "translate-x-0 shadow-xl" : "-translate-x-full")
          : cn("sticky top-0 transition-[width] duration-150", recolhida ? "w-[60px]" : "w-60"),
      )}
      aria-label="Navegação principal"
      aria-hidden={celular && !aberta ? true : undefined}
      inert={celular && !aberta ? true : undefined}
    >
      <div className={cn("flex h-14 items-center gap-2.5 border-b border-borda", recolhida ? "justify-center" : "px-4")}>
        <svg viewBox="0 0 32 32" aria-hidden className="size-7 shrink-0">
          <rect width="32" height="32" rx="8" className="fill-marca" />
          <path d="M10 8h8l5 5v11a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z" fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
          <path d="M12 17l3 3 5-6" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {!recolhida && (
          <span className="text-[15px] font-semibold tracking-tight">
            Contask <span className="text-destaque">NF</span>
          </span>
        )}
        {celular && (
          <button onClick={fechar} aria-label="Fechar menu" className="ml-auto rounded-lg p-2 text-texto-2 hover:bg-superficie-2">
            <X className="size-4" />
          </button>
        )}
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {itens.map(({ rota, rotulo, icone: Icone }) => {
          const casa = (r: string) => pathname === r || pathname.startsWith(`${r}/`);
          // /admin/leads e /admin/monitoramento acendem só o próprio item, não a Administração
          const ativa = casa(rota) && !itens.some((o) => o.rota.length > rota.length && o.rota.startsWith(rota) && casa(o.rota));
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

      <div className={cn("border-t border-borda p-2", celular && "hidden")}>
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
    </>
  );
}
