import * as TT from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export const TooltipProvider = TT.Provider;

export function Dica({ texto, lado = "right", children, ativo = true }: {
  texto: ReactNode;
  lado?: "top" | "right" | "bottom" | "left";
  children: ReactNode;
  ativo?: boolean;
}) {
  if (!ativo) return <>{children}</>;
  return (
    <TT.Root>
      <TT.Trigger asChild>{children}</TT.Trigger>
      <TT.Portal>
        <TT.Content
          side={lado}
          sideOffset={8}
          className="z-50 max-w-72 rounded-lg bg-texto px-2.5 py-1.5 text-xs text-fundo"
        >
          {texto}
        </TT.Content>
      </TT.Portal>
    </TT.Root>
  );
}
