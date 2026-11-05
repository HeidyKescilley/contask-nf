import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export function Copiar({ texto, exibir, className }: { texto: string; exibir?: string; className?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(texto).then(() => {
          setOk(true);
          setTimeout(() => setOk(false), 1200);
        });
      }}
      className={cn("group inline-flex items-center gap-1.5 rounded-md font-mono text-[13px] text-texto-2 hover:text-texto", className)}
      aria-label={`Copiar ${exibir ?? texto}`}
    >
      {exibir ?? texto}
      {ok ? <Check className="size-3.5 text-autorizada" aria-hidden /> : <Copy className="size-3.5 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden />}
    </button>
  );
}
