import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2, LogIn, ShieldCheck } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { type Usuario, useSessao } from "@/lib/sessao";
import { MenuTema } from "@/layout/MenuTema";

function Moldura({ titulo, descricao, children }: { titulo: string; descricao: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-fundo">
      <div className="flex justify-end p-4">
        <MenuTema />
      </div>
      <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-4 pb-24">
        <div className="mb-6 text-center">
          <div className="text-xl font-semibold tracking-tight">
            Contask <span className="text-destaque">NF</span>
          </div>
        </div>
        <section className="rounded-2xl border border-borda bg-superficie p-6 shadow-sm">
          <h1 className="text-lg font-semibold">{titulo}</h1>
          <p className="mt-1 text-sm text-texto-2">{descricao}</p>
          <div className="mt-5">{children}</div>
        </section>
      </main>
    </div>
  );
}

function CampoSenha({ rotulo, valor, mudar, autoComplete, ajuda, autoFocus }: {
  rotulo: string;
  valor: string;
  mudar: (v: string) => void;
  autoComplete: string;
  ajuda?: string;
  autoFocus?: boolean;
}) {
  const [ver, setVer] = useState(false);
  return (
    <Campo rotulo={rotulo} ajuda={ajuda}>
      {(p) => (
        <div className="relative">
          <Input {...p} type={ver ? "text" : "password"} value={valor} onChange={(e) => mudar(e.target.value)}
            autoComplete={autoComplete} autoFocus={autoFocus} required className="pr-10" />
          <button type="button" onClick={() => setVer((v) => !v)}
            className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-texto-2 hover:text-texto"
            aria-label={ver ? "Ocultar senha" : "Mostrar senha"}>
            {ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </div>
      )}
    </Campo>
  );
}

export function Entrar() {
  const sessao = useSessao();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const local = useLocation();
  const voltar = (local.state as { voltar?: string } | null)?.voltar || "/dashboard";
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const entrar = useMutation({
    mutationFn: () => api<{ usuario: Usuario }>("/api/auth/entrar", { method: "POST", body: JSON.stringify({ email, senha }) }),
    onSuccess: async (r) => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "sessao" });
      await qc.invalidateQueries({ queryKey: ["sessao"] });
      navegar(r.usuario.trocar_senha ? "/trocar-senha" : voltar, { replace: true });
    },
    onSettled: () => setSenha(""),
  });

  if (sessao.isLoading) return <Moldura titulo="Entrar" descricao="Carregando..."><Esqueleto className="h-32 w-full" /></Moldura>;
  if (sessao.data?.usuario?.trocar_senha) return <Navigate to="/trocar-senha" replace />;
  if (sessao.data?.usuario) return <Navigate to={voltar} replace />;

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    entrar.mutate();
  };
  return (
    <Moldura titulo="Entrar" descricao="Acesse as notas fiscais das empresas do seu escritório.">
      <form onSubmit={enviar} className="space-y-4" noValidate={false}>
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
        <p className="text-center text-xs text-texto-2">Esqueceu a senha? Fale com o suporte do Contask NF.</p>
        {sessao.data?.cadastro === "fechado" ? (
          <p className="text-center text-sm text-texto-2">Não tem conta? Peça o acesso ao suporte do Contask NF.</p>
        ) : (
          <p className="text-center text-sm text-texto-2">
            Não tem conta? <Link to="/cadastrar" className="text-destaque hover:underline">Cadastre o escritório</Link>
          </p>
        )}
      </form>
    </Moldura>
  );
}

export function Cadastrar() {
  const sessao = useSessao();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [convite, setConvite] = useState("");
  const pedeConvite = sessao.data?.cadastro === "convite";
  const diferentes = confirma.length > 0 && confirma !== senha;
  const cadastrar = useMutation({
    mutationFn: () => api<{ usuario: Usuario }>("/api/auth/cadastrar", {
      method: "POST", body: JSON.stringify({ nome, email, senha, convite: pedeConvite ? convite : null }),
    }),
    onSuccess: async () => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "sessao" });
      await qc.invalidateQueries({ queryKey: ["sessao"] });
      navegar("/dashboard", { replace: true });
    },
    onSettled: () => setSenha(""),
  });

  if (sessao.isLoading) return <Moldura titulo="Cadastrar" descricao="Carregando..."><Esqueleto className="h-40 w-full" /></Moldura>;
  if (sessao.data?.usuario) return <Navigate to="/dashboard" replace />;
  if (sessao.data?.cadastro === "fechado") {
    return (
      <Moldura titulo="Cadastrar" descricao="O cadastro de novos escritórios é feito pelo suporte do Contask NF.">
        <p className="text-sm text-texto-2">Peça o acesso ao suporte: você recebe o e-mail de entrada e uma senha inicial, que é trocada no primeiro acesso.</p>
        <p className="mt-4 text-center text-sm"><Link to="/entrar" className="text-destaque hover:underline">Voltar para entrar</Link></p>
      </Moldura>
    );
  }

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (!diferentes) cadastrar.mutate();
  };
  return (
    <Moldura titulo="Cadastrar" descricao="Crie o escritório e o primeiro acesso. Você vê todas as empresas dele.">
      <form onSubmit={enviar} className="space-y-4">
        {sessao.isError && <Aviso tom="erro">{(sessao.error as Error).message}</Aviso>}
        {cadastrar.isError && <Aviso tom="erro">{(cadastrar.error as Error).message}</Aviso>}
        {pedeConvite && (
          <Campo rotulo="Código de convite" ajuda="Enviado pelo suporte do Contask NF. Vale uma vez.">
            {(p) => <Input {...p} value={convite} onChange={(e) => setConvite(e.target.value.toUpperCase())} autoComplete="off" required />}
          </Campo>
        )}
        <Campo rotulo="Nome">
          {(p) => <Input {...p} value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name" autoFocus required />}
        </Campo>
        <Campo rotulo="E-mail">
          {(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            autoComplete="username" required />}
        </Campo>
        <CampoSenha rotulo="Senha" valor={senha} mudar={setSenha} autoComplete="new-password"
          ajuda="Pelo menos 10 caracteres, com maiúsculas, minúsculas e número." />
        <Campo rotulo="Repita a senha" erro={diferentes ? "As senhas não são iguais." : undefined}>
          {(p) => <Input {...p} type="password" value={confirma} onChange={(e) => setConfirma(e.target.value)}
            autoComplete="new-password" required />}
        </Campo>
        <Button type="submit" variante="primario" className="w-full"
          disabled={cadastrar.isPending || !nome.trim() || !email || !senha || !confirma || diferentes || (pedeConvite && !convite.trim())}>
          {cadastrar.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Criar escritório
        </Button>
        <p className="text-center text-sm text-texto-2">
          Já tem conta? <Link to="/entrar" className="text-destaque hover:underline">Entrar</Link>
        </p>
      </form>
    </Moldura>
  );
}

export function TrocarSenha() {
  const sessao = useSessao();
  const qc = useQueryClient();
  const navegar = useNavigate();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const trocar = useMutation({
    mutationFn: () => api<{ usuario: Usuario }>("/api/auth/senha", {
      method: "POST", body: JSON.stringify({ senha_atual: atual, senha_nova: nova }),
    }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["sessao"] });
      navegar("/dashboard", { replace: true });
    },
  });

  if (sessao.isLoading) return <Moldura titulo="Trocar senha" descricao="Carregando..."><Esqueleto className="h-48 w-full" /></Moldura>;
  if (sessao.isError) return <Moldura titulo="Trocar senha" descricao="Não foi possível carregar."><Aviso tom="erro">{(sessao.error as Error).message}</Aviso></Moldura>;
  if (!sessao.data?.usuario) return <Navigate to="/entrar" replace />;

  const obrigatoria = sessao.data.usuario.trocar_senha;
  const diferentes = confirma.length > 0 && confirma !== nova;
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (!diferentes) trocar.mutate();
  };
  return (
    <Moldura titulo={obrigatoria ? "Crie sua senha" : "Trocar senha"}
      descricao={obrigatoria ? "Primeiro acesso: troque a senha inicial por uma que só você conheça." : "As outras sessões abertas com a senha antiga serão encerradas."}>
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
        {!obrigatoria && (
          <Button type="button" variante="fantasma" className="w-full" onClick={() => navegar(-1)}>Cancelar</Button>
        )}
      </form>
    </Moldura>
  );
}
