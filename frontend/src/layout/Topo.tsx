import { RefreshCw } from "lucide-react";
import { Dica } from "@/components/ui/tooltip";
import { useBuscas, useCentral } from "@/lib/buscas";
import { BuscaRapida } from "./BuscaRapida";
import { MenuTema } from "./MenuTema";
import { MenuUsuario } from "./MenuUsuario";
import { SeletorEmpresa } from "./SeletorEmpresa";

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
        className="flex h-9 items-center gap-2 rounded-xl px-3 text-sm text-texto-2 hover:bg-superficie-2 hover:text-texto"
        aria-label={`Central de Buscas: ${texto}`}
      >
        <RefreshCw className={ativas ? "size-4 animate-spin text-destaque" : "size-4"} aria-hidden />
        <span>Buscas</span>
        <span className="rounded-full bg-superficie-2 px-1.5 font-mono text-[11px] tabular-nums">{ativas || naFila}</span>
      </button>
    </Dica>
  );
}

export function Topo() {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-borda bg-superficie/90 px-5 backdrop-blur">
      <SeletorEmpresa />
      <div className="flex-1" />
      <BuscaRapida />
      <IndicadorBuscas />
      <MenuTema />
      <MenuUsuario />
    </header>
  );
}
