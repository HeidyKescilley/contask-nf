import { clsx, type ClassValue } from "clsx";
import { useSyncExternalStore } from "react";
import { twMerge } from "tailwind-merge";

const CELULAR = "(max-width: 767px)";

/** true abaixo de 768 px (o menu lateral vira gaveta). */
export function useCelular(): boolean {
  return useSyncExternalStore(
    (avisar) => {
      const m = window.matchMedia(CELULAR);
      m.addEventListener("change", avisar);
      return () => m.removeEventListener("change", avisar);
    },
    () => window.matchMedia(CELULAR).matches,
    () => false,
  );
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function lerLocal(chave: string): string | null {
  try {
    return localStorage.getItem(chave);
  } catch {
    return null;
  }
}

export function gravarLocal(chave: string, valor: string) {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    /* armazenamento indisponível: segue sem persistir */
  }
}
