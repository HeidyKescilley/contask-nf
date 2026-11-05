import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { type PreferenciaTema, useTema } from "@/lib/tema";

const ROTULO: Record<PreferenciaTema, string> = { claro: "Claro", escuro: "Escuro", sistema: "Sistema" };

export function MenuTema() {
  const { preferencia, escuro, definir } = useTema();
  const Icone = preferencia === "sistema" ? Monitor : escuro ? Moon : Sun;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variante="fantasma" tamanho="icone" aria-label={`Tema: ${ROTULO[preferencia]}`} data-testid="menu-tema">
          <Icone />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Tema</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={preferencia} onValueChange={(v) => definir(v as PreferenciaTema)}>
          <DropdownMenuRadioItem value="claro"><Sun /> Claro</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="escuro"><Moon /> Escuro</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="sistema"><Monitor /> Sistema</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
