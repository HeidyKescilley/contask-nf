import { AlertTriangle, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Esqueleto({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-superficie-2", className)} aria-hidden />;
}

export function EstadoVazio({ icone: Icone, titulo, children, acao }: {
  icone: LucideIcon;
  titulo: string;
  children?: ReactNode;
  acao?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-borda-forte bg-superficie px-6 py-14 text-center">
      <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-destaque-suave text-destaque">
        <Icone className="size-5" aria-hidden />
      </div>
      <h2 className="text-[15px] font-semibold">{titulo}</h2>
      {children && <p className="mt-1.5 max-w-md text-sm text-texto-2">{children}</p>}
      {acao && <div className="mt-5">{acao}</div>}
    </div>
  );
}

export function EstadoErro({ mensagem, tentarDeNovo }: { mensagem: string; tentarDeNovo?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-cancelada/30 bg-cancelada-suave px-4 py-3 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-cancelada" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">Algo deu errado</p>
        <p className="text-texto-2">{mensagem}</p>
      </div>
      {tentarDeNovo && (
        <button onClick={tentarDeNovo} className="font-medium text-destaque hover:underline">
          Tentar de novo
        </button>
      )}
    </div>
  );
}

export function Cabecalho({ titulo, descricao, acoes }: { titulo: string; descricao?: string; acoes?: ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{titulo}</h1>
        {descricao && <p className="mt-1 text-sm text-texto-2">{descricao}</p>}
      </div>
      {acoes}
    </div>
  );
}
