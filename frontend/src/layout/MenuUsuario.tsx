import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

/** Só aparece quando o login está ativo (servidor na internet). */
export function MenuUsuario() {
  const { data } = useSessao();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const sair = useMutation({
    mutationFn: () => api<void>("/api/auth/sair", { method: "POST" }),
    onSuccess: async () => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "sessao" });
      await qc.invalidateQueries({ queryKey: ["sessao"] });
      navegar("/entrar", { replace: true });
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const u = data?.usuario;
  if (!data?.login_ativo || !u) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variante="fantasma" tamanho="icone" aria-label={`Conta: ${u.nome}`}>
          <UserRound />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel>
          <div className="truncate text-sm font-medium text-texto">{u.nome}</div>
          <div className="truncate text-xs font-normal text-texto-2">{u.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navegar("/trocar-senha")}><KeyRound /> Trocar senha</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => sair.mutate()} disabled={sair.isPending}><LogOut /> Sair</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
