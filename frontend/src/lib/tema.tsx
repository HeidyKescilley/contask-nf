import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { gravarLocal, lerLocal } from "./utils";

export type PreferenciaTema = "claro" | "escuro" | "sistema";
const CHAVE = "contask-tema";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

function aplicar(pref: PreferenciaTema) {
  const escuro = pref === "escuro" || (pref === "sistema" && media().matches);
  const el = document.documentElement;
  el.classList.add("sem-transicao");
  el.classList.toggle("dark", escuro);
  el.style.colorScheme = escuro ? "dark" : "light";
  el.dataset.tema = pref;
  // Reativa as transições depois que o navegador pintar o novo tema
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.remove("sem-transicao")));
  return escuro;
}

interface Ctx {
  preferencia: PreferenciaTema;
  escuro: boolean;
  definir: (p: PreferenciaTema) => void;
}
const TemaContext = createContext<Ctx | null>(null);

export function TemaProvider({ children }: { children: ReactNode }) {
  const [preferencia, setPreferencia] = useState<PreferenciaTema>(
    () => (lerLocal(CHAVE) as PreferenciaTema) || "sistema",
  );
  const [escuro, setEscuro] = useState(() => document.documentElement.classList.contains("dark"));

  const definir = useCallback((p: PreferenciaTema) => {
    gravarLocal(CHAVE, p);
    setPreferencia(p);
    setEscuro(aplicar(p));
  }, []);

  // Acompanha a mudança do tema do sistema quando a preferência é "sistema"
  useEffect(() => {
    if (preferencia !== "sistema") return;
    const mq = media();
    const ouvir = () => setEscuro(aplicar("sistema"));
    mq.addEventListener("change", ouvir);
    return () => mq.removeEventListener("change", ouvir);
  }, [preferencia]);

  // Sincroniza entre abas
  useEffect(() => {
    const ouvir = (e: StorageEvent) => {
      if (e.key === CHAVE && e.newValue) {
        const p = e.newValue as PreferenciaTema;
        setPreferencia(p);
        setEscuro(aplicar(p));
      }
    };
    window.addEventListener("storage", ouvir);
    return () => window.removeEventListener("storage", ouvir);
  }, []);

  return <TemaContext.Provider value={{ preferencia, escuro, definir }}>{children}</TemaContext.Provider>;
}

export function useTema() {
  const ctx = useContext(TemaContext);
  if (!ctx) throw new Error("useTema fora do TemaProvider");
  return ctx;
}
