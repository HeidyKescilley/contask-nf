import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export const estiloCampo =
  "h-9 w-full rounded-xl border border-borda bg-superficie px-3 text-sm text-texto outline-none transition-colors duration-150 placeholder:text-texto-2/70 hover:border-borda-forte focus-visible:border-destaque focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destaque/25 disabled:opacity-60 aria-[invalid=true]:border-cancelada";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(estiloCampo, className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(estiloCampo, "pr-8", className)} {...props} />;
}

/** Rótulo + controle + ajuda/erro, com ids ligados para leitores de tela. */
export function Campo({ rotulo, erro, ajuda, obrigatorio, className, children }: {
  rotulo: string;
  erro?: string;
  ajuda?: ReactNode;
  obrigatorio?: boolean;
  className?: string;
  children: (props: { id: string; "aria-invalid": boolean; "aria-describedby"?: string }) => ReactNode;
}) {
  const id = useId();
  const desc = erro || ajuda ? `${id}-desc` : undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-[13px] font-medium">
        {rotulo}
        {obrigatorio && <span className="text-cancelada" aria-hidden> *</span>}
      </label>
      {children({ id, "aria-invalid": !!erro, "aria-describedby": desc })}
      {(erro || ajuda) && (
        <p id={desc} className={cn("text-xs", erro ? "text-cancelada" : "text-texto-2")}>
          {erro || ajuda}
        </p>
      )}
    </div>
  );
}

export function Aviso({ tom = "alerta", children }: { tom?: "alerta" | "info" | "erro"; children: ReactNode }) {
  return (
    <div
      role={tom === "erro" ? "alert" : "status"}
      className={cn(
        "rounded-xl border px-3.5 py-2.5 text-sm",
        tom === "alerta" && "border-rejeitada/30 bg-rejeitada-suave",
        tom === "info" && "border-destaque/25 bg-destaque-suave",
        tom === "erro" && "border-cancelada/30 bg-cancelada-suave",
      )}
    >
      {children}
    </div>
  );
}
