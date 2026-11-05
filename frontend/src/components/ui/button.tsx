import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const variantes = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variante: {
        primario: "bg-destaque text-destaque-texto hover:bg-destaque/90",
        secundario: "border border-borda bg-superficie text-texto hover:bg-superficie-2",
        fantasma: "text-texto-2 hover:bg-superficie-2 hover:text-texto",
      },
      tamanho: {
        padrao: "h-9 px-3.5",
        pequeno: "h-8 px-2.5 text-[13px]",
        icone: "size-9",
      },
    },
    defaultVariants: { variante: "secundario", tamanho: "padrao" },
  },
);

export function Button({
  className,
  variante,
  tamanho,
  asChild,
  ...props
}: ComponentProps<"button"> & VariantProps<typeof variantes> & { asChild?: boolean }) {
  const C = asChild ? Slot : "button";
  return <C className={cn(variantes({ variante, tamanho }), className)} {...props} />;
}
