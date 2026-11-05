import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { NAVEGACAO } from "./navegacao";

const normalizar = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** Ctrl+K: por enquanto navega entre as páginas. Nas próximas fases, busca empresas e notas. */
export function BuscaRapida() {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [termo, setTermo] = useState("");
  const [ativo, setAtivo] = useState(0);
  const navegar = useNavigate();
  const { search } = useLocation();

  const itens = useMemo(
    () => NAVEGACAO.filter((i) => normalizar(`${i.rotulo} ${i.descricao}`).includes(normalizar(termo))),
    [termo],
  );

  const abrir = () => {
    setTermo("");
    setAtivo(0);
    dialogo.current?.showModal();
  };
  const fechar = () => dialogo.current?.close();
  const escolher = (rota: string) => {
    fechar();
    navegar({ pathname: rota, search });
  };

  useEffect(() => {
    const atalho = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (dialogo.current?.open) fechar();
        else abrir();
      }
    };
    window.addEventListener("keydown", atalho);
    return () => window.removeEventListener("keydown", atalho);
  }, []);

  return (
    <>
      <button
        onClick={abrir}
        className="flex h-9 w-56 shrink-0 items-center xl:w-72 gap-2 rounded-xl border border-borda bg-fundo px-3 text-sm text-texto-2 transition-colors duration-150 hover:border-borda-forte"
      >
        <Search className="size-4" aria-hidden />
        <span className="flex-1 text-left">Buscar…</span>
        <kbd className="rounded-md border border-borda bg-superficie px-1.5 font-mono text-[11px]">Ctrl K</kbd>
      </button>

      <dialog
        ref={dialogo}
        aria-label="Busca rápida"
        onClick={(e) => e.target === dialogo.current && fechar()}
        className="m-auto mt-[12vh] w-[min(560px,90vw)] rounded-xl border border-borda bg-superficie p-0 text-texto shadow-[0_24px_48px_-16px_rgb(0_0_0/0.35)] backdrop:bg-black/40"
      >
        <div className="flex items-center gap-2 border-b border-borda px-4">
          <Search className="size-4 text-texto-2" aria-hidden />
          <input
            autoFocus
            value={termo}
            onChange={(e) => {
              setTermo(e.target.value);
              setAtivo(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setAtivo((a) => Math.min(a + 1, itens.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setAtivo((a) => Math.max(a - 1, 0)); }
              if (e.key === "Enter" && itens[ativo]) escolher(itens[ativo].rota);
            }}
            placeholder="Ir para…"
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-texto-2"
            role="combobox"
            aria-expanded="true"
            aria-controls="busca-rapida-lista"
            aria-activedescendant={itens[ativo] ? `br-${itens[ativo].rota}` : undefined}
          />
        </div>
        <ul id="busca-rapida-lista" role="listbox" className="max-h-80 overflow-auto p-1.5">
          {itens.length === 0 && <li className="px-3 py-6 text-center text-sm text-texto-2">Nada encontrado.</li>}
          {itens.map((i, idx) => (
            <li
              key={i.rota}
              id={`br-${i.rota}`}
              role="option"
              aria-selected={idx === ativo}
              onMouseMove={() => setAtivo(idx)}
              onClick={() => escolher(i.rota)}
              className={cn(
                "flex cursor-default items-center gap-3 rounded-lg px-3 py-2 text-sm",
                idx === ativo && "bg-superficie-2",
              )}
            >
              <i.icone className="size-4 text-texto-2" aria-hidden />
              <span className="font-medium">{i.rotulo}</span>
              <span className="truncate text-texto-2">{i.descricao}</span>
              {idx === ativo && <CornerDownLeft className="ml-auto size-3.5 text-texto-2" aria-hidden />}
            </li>
          ))}
        </ul>
      </dialog>
    </>
  );
}
