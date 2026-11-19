import { Menu, RefreshCw } from "lucide-react";
import { Dica } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useBuscas, useCentral } from "@/lib/buscas";
import { BuscaRapida } from "./BuscaRapida";
import { MenuTema } from "./MenuTema";
import { MenuUsuario } from "./MenuUsuario";
import { SeletorEmpresa } from "./SeletorEmpresa";
import { BotaoSuporte } from "./Suporte";

/** Indicador da Central de Buscas: abre o painel lateral em qualquer tela. */
function IndicadorBuscas() {
  const { data } = useBuscas();
  const { abrir } = useCentral();
  const ativas = data?.rodando ?? 0;
  const naFila = data?.na_fila ?? 0;
  const texto = ativas ? `${ativas} busca(s) em andamento` : naFila ? `${naFila} busca(s) na fila` : "Nenhuma busca em andamento";
  return (
    <Dica texto={texto} lado="bottom">
      <button
        onClick={() => abrir()}
        className="flex h-9 shrink-0 items-center gap-2 rounded-xl px-2 text-sm text-texto-2 hover:bg-superficie-2 hover:text-texto xl:px-3"
        aria-label={`Central de Buscas: ${texto}`}
      >
        <RefreshCw className={ativas ? "size-4 animate-spin text-destaque" : "size-4"} aria-hidden />
        <span className="hidden xl:inline">Buscas</span>
        <span className={cn("rounded-full bg-superficie-2 px-1.5 font-mono text-[11px] tabular-nums", !(ativas || naFila) && "hidden sm:inline")}>{ativas || naFila}</span>
      </button>
    </Dica>
  );
}

export function Topo({ abrirMenu }: { abrirMenu: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-1 border-b border-borda bg-superficie/90 px-2 backdrop-blur sm:gap-2 md:gap-3 md:px-5">
      <button onClick={abrirMenu} aria-label="Abrir menu" className="flex size-9 shrink-0 items-center justify-center rounded-xl text-texto-2 hover:bg-superficie-2 md:hidden">
        <Menu className="size-5" aria-hidden />
      </button>
      {/* data-privado: nomes de empresa e de usuário nunca viram rótulo de clique no monitoramento */}
      <div data-privado className="min-w-0 flex-1 md:flex-none"><SeletorEmpresa /></div>
      <div className="hidden flex-1 md:block" />
      <div data-privado className="shrink-0"><BuscaRapida /></div>
      <IndicadorBuscas />
      <BotaoSuporte />
      {/* No celular o tema segue o do aparelho: o botão sai para dar espaço ao seletor de empresa */}
      <div className="hidden shrink-0 sm:block"><MenuTema /></div>
      <div data-privado className="shrink-0"><MenuUsuario /></div>
    </header>
  );
}
