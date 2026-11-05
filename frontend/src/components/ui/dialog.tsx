import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ titulo, descricao, children }: { titulo: string; descricao?: ReactNode; children: ReactNode }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/40" />
      <D.Content className="fixed left-1/2 top-[15vh] z-50 w-[min(480px,92vw)] -translate-x-1/2 rounded-xl border border-borda bg-superficie p-5 text-texto shadow-[0_24px_48px_-16px_rgb(0_0_0/0.35)]">
        <D.Title className="text-base font-semibold">{titulo}</D.Title>
        {descricao && <D.Description className="mt-1.5 text-sm text-texto-2">{descricao}</D.Description>}
        <div className="mt-4">{children}</div>
        <D.Close className="absolute right-3 top-3 rounded-lg p-1.5 text-texto-2 hover:bg-superficie-2" aria-label="Fechar">
          <X className="size-4" />
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}
