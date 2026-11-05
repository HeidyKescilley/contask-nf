import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Passos({ passos, atual }: { passos: string[]; atual: number }) {
  return (
    <ol className="mb-6 flex items-center gap-3" aria-label="Etapas">
      {passos.map((p, i) => {
        const feito = i < atual;
        const ativo = i === atual;
        return (
          <li key={p} className="flex items-center gap-3" aria-current={ativo ? "step" : undefined}>
            <span
              className={cn(
                "flex size-7 items-center justify-center rounded-full border text-xs font-semibold tabular-nums",
                feito && "border-destaque bg-destaque text-destaque-texto",
                ativo && "border-destaque text-destaque",
                !feito && !ativo && "border-borda-forte text-texto-2",
              )}
            >
              {feito ? <Check className="size-3.5" aria-hidden /> : i + 1}
            </span>
            <span className={cn("text-sm", ativo ? "font-medium" : "text-texto-2")}>{p}</span>
            {i < passos.length - 1 && <span className="h-px w-10 bg-borda-forte" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

export function Painel({ titulo, descricao, children }: { titulo?: string; descricao?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-borda bg-superficie p-5">
      {titulo && <h2 className="text-[15px] font-semibold">{titulo}</h2>}
      {descricao && <p className="mt-1 text-sm text-texto-2">{descricao}</p>}
      <div className={titulo || descricao ? "mt-4" : undefined}>{children}</div>
    </section>
  );
}

export function LinhaResumo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-4 border-b border-borda py-2.5 text-sm last:border-0">
      <dt className="text-texto-2">{rotulo}</dt>
      <dd>{children}</dd>
    </div>
  );
}
