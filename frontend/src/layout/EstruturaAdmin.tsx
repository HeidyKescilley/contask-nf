import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, LogIn, LogOut, Menu, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CampoSenha, Moldura } from "@/features/acesso/Acesso";
import { api } from "@/lib/api";
import { CHAVE_SESSAO_ADMIN, type SessaoAdmin, useSessaoAdmin } from "@/lib/sessaoAdmin";
import { gravarLocal, lerLocal } from "@/lib/utils";
import { BarraLateral } from "./BarraLateral";
import { MenuTema } from "./MenuTema";
import { NAVEGACAO_ADMIN } from "./navegacao";

const CHAVE_MENU = "contask-admin-menu-recolhido";

/** Remove do cache tudo da administração (sem tocar na sessão do sistema). */
function limparAdmin(qc: ReturnType<typeof useQueryClient>) {
  qc.removeQueries({ predicate: (q) => ["admin", "monitoramento"].includes(String(q.queryKey[0])) });
}

/** Login da administração: separado do login do sistema (cookie e sessão próprios, 12 horas). */
export function EntrarAdmin() {
  const sessao = useSessaoAdmin();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const local = useLocation();
  const voltar = (local.state as { voltar?: string } | null)?.voltar || "/admin";
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const entrar = useMutation({
    mutationFn: () => api<SessaoAdmin>("/api/admin/auth/entrar", { method: "POST", body: JSON.stringify({ email, senha }) }),
    onSuccess: (r) => {
      limparAdmin(qc);
      qc.setQueryData(CHAVE_SESSAO_ADMIN, r);
      navegar(voltar, { replace: true });
    },
    onSettled: () => setSenha(""),
  });

  if (sessao.isLoading) return <Moldura area="Administração" titulo="Entrar" descricao="Carregando..."><Esqueleto className="h-32 w-full" /></Moldura>;
  if (sessao.data?.usuario) return <Navigate to={voltar} replace />;

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    entrar.mutate();
  };
  return (
    <Moldura area="Administração" titulo="Entrar na administração"
      descricao="Gestão dos clientes do Contask NF. O acesso é separado do sistema e vale por 12 horas.">
      <form onSubmit={enviar} className="space-y-4">
        {sessao.isError && <Aviso tom="erro">{(sessao.error as Error).message}</Aviso>}
        {entrar.isError && <Aviso tom="erro">{(entrar.error as Error).message}</Aviso>}
        <Campo rotulo="E-mail">
          {(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            autoComplete="username" autoFocus required />}
        </Campo>
        <CampoSenha rotulo="Senha" valor={senha} mudar={setSenha} autoComplete="current-password" />
        <Button type="submit" variante="primario" className="w-full" disabled={entrar.isPending || !email || !senha}>
          {entrar.isPending ? <Loader2 className="animate-spin" /> : <LogIn />} Entrar
        </Button>
      </form>
    </Moldura>
  );
}

/** Troca da própria senha na administração; obrigatória com a senha inicial, antes de qualquer tela. */
export function TrocarSenhaAdmin() {
  const sessao = useSessaoAdmin();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const trocar = useMutation({
    mutationFn: () => api<SessaoAdmin>("/api/admin/auth/senha", {
      method: "POST", body: JSON.stringify({ senha_atual: atual, senha_nova: nova }),
    }),
    onSuccess: (r) => {
      qc.setQueryData(CHAVE_SESSAO_ADMIN, r);
      toast.success("Senha salva.");
      navegar("/admin", { replace: true });
    },
  });
  const obrigatoria = !!sessao.data?.usuario?.trocar_senha;
  const diferentes = confirma.length > 0 && confirma !== nova;
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (!diferentes) trocar.mutate();
  };
  return (
    <Moldura area="Administração" titulo={obrigatoria ? "Crie sua senha" : "Trocar senha"}
      descricao={obrigatoria ? "Primeiro acesso: troque a senha inicial por uma que só você conheça."
        : "As outras sessões abertas com a senha antiga serão encerradas (inclusive no sistema, se você também usa)."}>
      <form onSubmit={enviar} className="space-y-4">
        {trocar.isError && <Aviso tom="erro">{(trocar.error as Error).message}</Aviso>}
        <CampoSenha rotulo={obrigatoria ? "Senha inicial" : "Senha atual"} valor={atual} mudar={setAtual} autoComplete="current-password" autoFocus />
        <CampoSenha rotulo="Nova senha" valor={nova} mudar={setNova} autoComplete="new-password"
          ajuda="Pelo menos 10 caracteres, com maiúsculas, minúsculas e número." />
        <Campo rotulo="Repita a nova senha" erro={diferentes ? "As senhas não são iguais." : undefined}>
          {(p) => <Input {...p} type="password" value={confirma} onChange={(e) => setConfirma(e.target.value)} autoComplete="new-password" required />}
        </Campo>
        <Button type="submit" variante="primario" className="w-full" disabled={trocar.isPending || !atual || !nova || !confirma || diferentes}>
          {trocar.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Salvar nova senha
        </Button>
        {!obrigatoria && <Button type="button" variante="fantasma" className="w-full" onClick={() => navegar(-1)}>Cancelar</Button>}
      </form>
    </Moldura>
  );
}

function MenuAdmin() {
  const { data } = useSessaoAdmin();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const sair = useMutation({
    mutationFn: () => api<void>("/api/admin/auth/sair", { method: "POST" }),
    onSuccess: () => {
      limparAdmin(qc);
      qc.setQueryData(CHAVE_SESSAO_ADMIN, { usuario: null });
      navegar("/admin/entrar", { replace: true });
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const u = data?.usuario;
  if (!u) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variante="fantasma" tamanho="icone" aria-label={`Conta: ${u.nome}`}><UserRound /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel>
          <div className="truncate text-sm font-medium text-texto">{u.nome}</div>
          <div className="truncate text-xs font-normal text-texto-2">{u.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navegar("/admin/senha")}><KeyRound /> Trocar senha</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => sair.mutate()} disabled={sair.isPending}><LogOut /> Sair da administração</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Ambiente da administração: menu e topo próprios, sem as telas e funções dos clientes. */
export function EstruturaAdmin() {
  const [recolhida, setRecolhida] = useState(() => lerLocal(CHAVE_MENU) === "1");
  const alternar = () => setRecolhida((r) => { gravarLocal(CHAVE_MENU, r ? "0" : "1"); return !r; });
  const [menuAberto, setMenuAberto] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => { setMenuAberto(false); }, [pathname]);
  useEffect(() => {
    const antes = document.title;
    document.title = "Administração · Contask NF";
    return () => { document.title = antes; };
  }, []);
  // Senha inicial: nada da administração abre antes da troca
  if (useSessaoAdmin().data?.usuario?.trocar_senha) return <Navigate to="/admin/senha" replace />;

  return (
    <div className="flex min-h-screen">
      <BarraLateral itens={NAVEGACAO_ADMIN} area="Administração" recolhida={recolhida} alternar={alternar}
        aberta={menuAberto} fechar={() => setMenuAberto(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-borda bg-superficie/90 px-2 backdrop-blur md:px-5">
          <button onClick={() => setMenuAberto(true)} aria-label="Abrir menu"
            className="flex size-9 shrink-0 items-center justify-center rounded-xl text-texto-2 hover:bg-superficie-2 md:hidden">
            <Menu className="size-5" aria-hidden />
          </button>
          <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-texto-2">
            <ShieldCheck className="size-4 shrink-0 text-destaque" aria-hidden />
            <span className="truncate">Administração<span className="hidden sm:inline"> do Contask NF</span></span>
          </span>
          <div className="flex-1" />
          <MenuTema />
          <MenuAdmin />
        </header>
        <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-4 sm:px-6 sm:py-6 min-[1800px]:max-w-[1600px]">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
