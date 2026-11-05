import * as DM from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const DropdownMenu = DM.Root;
export const DropdownMenuTrigger = DM.Trigger;
export const DropdownMenuRadioGroup = DM.RadioGroup;

export function DropdownMenuContent({ className, sideOffset = 6, ...props }: ComponentProps<typeof DM.Content>) {
  return (
    <DM.Portal>
      <DM.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-44 rounded-xl border border-borda bg-superficie p-1 text-sm text-texto shadow-[0_8px_24px_-12px_rgb(0_0_0/0.25)]",
          className,
        )}
        {...props}
      />
    </DM.Portal>
  );
}

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof DM.Label>) {
  return <DM.Label className={cn("px-2 py-1.5 text-xs font-medium text-texto-2", className)} {...props} />;
}

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof DM.Item>) {
  return (
    <DM.Item
      className={cn(
        "relative flex cursor-default select-none items-center gap-2 rounded-lg px-2 py-1.5 outline-none data-[disabled]:opacity-50 data-[highlighted]:bg-superficie-2 [&_svg]:size-4 [&_svg]:text-texto-2",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({ className, ...props }: ComponentProps<typeof DM.Separator>) {
  return <DM.Separator className={cn("-mx-1 my-1 h-px bg-borda", className)} {...props} />;
}

export function DropdownMenuRadioItem({ className, children, ...props }: ComponentProps<typeof DM.RadioItem>) {
  return (
    <DM.RadioItem
      className={cn(
        "relative flex cursor-default select-none items-center gap-2 rounded-lg py-1.5 pl-2 pr-8 outline-none data-[highlighted]:bg-superficie-2 [&_svg]:size-4 [&_svg]:text-texto-2",
        className,
      )}
      {...props}
    >
      {children}
      <DM.ItemIndicator className="absolute right-2 inline-flex size-2 rounded-full bg-destaque" />
    </DM.RadioItem>
  );
}
