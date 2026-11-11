import { useMutation, useQuery } from "@tanstack/react-query";
import { Building2, KeyRound, Loader2, Plus, ShieldCheck, UserPlus, UserRoundCheck, UserRoundX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Copiar } from "@/components/Copiar";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { formatarDataHora } from "@/lib/formato";
import { useSessao } from "@/lib/sessao";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";

interface UsuarioAdm {
  id: number;
  escritorio_id: number;
  email: string;
  nome: string;
  ativo: boolean;
  trocar_senha: boolean;
  admin_sistema: boolean;
  criado_em: string;
  ultimo_acesso_em: string | null;
}
interface EscritorioAdm { id: number; nome: string; empresas: number; usuarios: UsuarioAdm[] }
interface ComSenha { usuario: UsuarioAdm; senha_inicial: string }

const CHAVE = ["admin", "escritorios"];

/** Painel do suporte do Contask: cria escritórios e usuários. Não mostra dados fiscais dos clientes. */
export function Administracao() {
  const sessao = useSessao();
  const admin = !!sessao.data?.usuario?.admin_sistema;
  const lista = useQuery({ queryKey: CHAVE, queryFn: () => api<EscritorioAdm[]>("/api/admin/escritorios"), enabled: admin });
  const [novoEsc, setNovoEsc] = useState(false);
  const [novoUsu, setNovoUsu] = useState<EscritorioAdm | null>(null);
  const [senha, setSenha] = useState<ComSenha | null>(null);

  if (sessao.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (!admin) {
    return <EstadoVazio icone={ShieldCheck} titulo="Área restrita">Só o administrador do sistema acessa esta página.</EstadoVazio>;
  }

  const total = lista.data?.reduce((s, e) => s + e.usuarios.length, 0) ?? 0;
  return (
    <>
      <Cabecalho titulo="Administração" descricao="Escritórios e usuários do sistema. A senha inicial aparece uma única vez: envie por um canal privado."
        acoes={<Button variante="primario" onClick={() => setNovoEsc(true)}><Plus /> Novo escritório</Button>} />
      {lista.isLoading && <Esqueleto className="h-64 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data?.length === 0 && (
        <EstadoVazio icone={Building2} titulo="Nenhum escritório" acao={<Button variante="primario" onClick={() => setNovoEsc(true)}><Plus /> Criar o primeiro</Button>}>
          Crie o escritório e o primeiro usuário dele.
        </EstadoVazio>
      )}
      {lista.data && lista.data.length > 0 && (
        <>
          <p className="mb-3 text-sm text-texto-2">{lista.data.length} escritório(s) · {total} usuário(s)</p>
          <ul className="space-y-3">
            {lista.data.map((e) => (
              <li key={e.id} className="rounded-xl border border-borda bg-superficie">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-borda px-4 py-3">
                  <div>
                    <h2 className="font-medium">{e.nome}</h2>
                    <p className="text-xs text-texto-2">id {e.id} · {e.empresas} empresa(s)</p>
                  </div>
                  <Button tamanho="pequeno" onClick={() => setNovoUsu(e)}><UserPlus /> Adicionar usuário</Button>
                </div>
                {e.usuarios.length === 0 ? <p className="px-4 py-3 text-sm text-texto-2">Sem usuários.</p> : (
                  <ul className="divide-y divide-borda">
                    {e.usuarios.map((u) => <LinhaUsuario key={u.id} u={u} eu={u.id === sessao.data?.usuario?.id} aoSenha={setSenha} />)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <NovoEscritorio aberto={novoEsc} aoFechar={() => setNovoEsc(false)} aoCriar={setSenha} />
      <NovoUsuario escritorio={novoUsu} aoFechar={() => setNovoUsu(null)} aoCriar={setSenha} />
      <SenhaInicial dados={senha} aoFechar={() => setSenha(null)} />
    </>
  );
}

function LinhaUsuario({ u, eu, aoSenha }: { u: UsuarioAdm; eu: boolean; aoSenha: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const atualizar = () => qc.invalidateQueries({ queryKey: CHAVE });
  const senha = useMutation({
    mutationFn: () => api<ComSenha>(`/api/admin/usuarios/${u.id}/senha`, { method: "POST" }),
    onSuccess: (r) => { atualizar(); aoSenha(r); },
    onError: (err) => toast.error((err as Error).message),
  });
  const ativo = useMutation({
    mutationFn: () => api<UsuarioAdm>(`/api/admin/usuarios/${u.id}/ativo`, { method: "PUT", body: JSON.stringify({ ativo: !u.ativo }) }),
    onSuccess: (r) => { atualizar(); toast.success(r.ativo ? "Acesso reativado." : "Acesso desativado: a pessoa saiu do sistema."); },
    onError: (err) => toast.error((err as Error).message),
  });
  return (
    <li className={cn("flex flex-wrap items-center gap-3 px-4 py-2.5", !u.ativo && "opacity-60")}>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {u.nome || u.email}
          {u.admin_sistema && <Selo tom="destaque" icone={ShieldCheck}>Admin</Selo>}
          {!u.ativo && <Selo tom="erro" icone={UserRoundX}>Desativado</Selo>}
          {u.ativo && u.trocar_senha && <Selo tom="alerta" icone={KeyRound}>Senha inicial</Selo>}
        </p>
        <p className="text-xs text-texto-2">{u.email} · último acesso: {u.ultimo_acesso_em ? formatarDataHora(u.ultimo_acesso_em) : "nunca"}</p>
      </div>
      {!eu && (
        <div className="flex gap-1">
          <Button tamanho="pequeno" variante="fantasma" disabled={senha.isPending}
            onClick={() => { if (window.confirm(`Gerar nova senha inicial para ${u.email}? A atual deixa de valer.`)) senha.mutate(); }}>
            {senha.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Nova senha
          </Button>
          <Button tamanho="pequeno" variante="fantasma" disabled={ativo.isPending}
            onClick={() => { if (u.ativo ? window.confirm(`Desativar o acesso de ${u.email}?`) : true) ativo.mutate(); }}>
            {u.ativo ? <><UserRoundX /> Desativar</> : <><UserRoundCheck /> Reativar</>}
          </Button>
        </div>
      )}
    </li>
  );
}

function NovoEscritorio({ aberto, aoFechar, aoCriar }: { aberto: boolean; aoFechar: () => void; aoCriar: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [pessoa, setPessoa] = useState("");
  const criar = useMutation({
    mutationFn: () => api<ComSenha>("/api/admin/escritorios", { method: "POST", body: JSON.stringify({ nome, email, nome_usuario: pessoa }) }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: CHAVE }); fechar(); aoCriar(r); },
  });
  const fechar = () => { setNome(""); setEmail(""); setPessoa(""); criar.reset(); aoFechar(); };
  const enviar = (ev: FormEvent) => { ev.preventDefault(); criar.mutate(); };
  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && !criar.isPending && fechar()}>
      <DialogContent titulo="Novo escritório" descricao="Cria o escritório e o primeiro usuário, com senha inicial de troca obrigatória.">
        <form className="space-y-4" onSubmit={enviar}>
          <Campo rotulo="Nome do escritório" obrigatorio>{(p) => <Input {...p} value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />}</Campo>
          <Campo rotulo="E-mail do primeiro usuário" obrigatorio>{(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}</Campo>
          <Campo rotulo="Nome da pessoa">{(p) => <Input {...p} value={pessoa} onChange={(e) => setPessoa(e.target.value)} />}</Campo>
          {criar.isError && <Aviso tom="erro">{(criar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={criar.isPending}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={criar.isPending || nome.trim().length < 2 || !email}>
              {criar.isPending && <Loader2 className="animate-spin" />} Criar escritório
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function NovoUsuario({ escritorio, aoFechar, aoCriar }: { escritorio: EscritorioAdm | null; aoFechar: () => void; aoCriar: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const criar = useMutation({
    mutationFn: () => api<ComSenha>(`/api/admin/escritorios/${escritorio!.id}/usuarios`, { method: "POST", body: JSON.stringify({ email, nome }) }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: CHAVE }); fechar(); aoCriar(r); },
  });
  const fechar = () => { setEmail(""); setNome(""); criar.reset(); aoFechar(); };
  return (
    <Dialog open={!!escritorio} onOpenChange={(v) => !v && !criar.isPending && fechar()}>
      <DialogContent titulo="Adicionar usuário" descricao={<>Novo acesso ao escritório <strong>{escritorio?.nome}</strong>. Ele vê todas as empresas do escritório.</>}>
        <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); criar.mutate(); }}>
          <Campo rotulo="E-mail" obrigatorio>{(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />}</Campo>
          <Campo rotulo="Nome">{(p) => <Input {...p} value={nome} onChange={(e) => setNome(e.target.value)} />}</Campo>
          {criar.isError && <Aviso tom="erro">{(criar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={criar.isPending}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={criar.isPending || !email}>
              {criar.isPending && <Loader2 className="animate-spin" />} Adicionar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SenhaInicial({ dados, aoFechar }: { dados: ComSenha | null; aoFechar: () => void }) {
  const endereco = window.location.origin;
  return (
    <Dialog open={!!dados} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent titulo="Senha inicial" descricao="Ela aparece só agora. Envie por um canal privado (WhatsApp direto, nunca em grupo). A pessoa troca no primeiro acesso.">
        {dados && (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-texto-2">Endereço</dt><dd><Copiar texto={endereco} exibir={endereco} /></dd></div>
            <div className="flex justify-between gap-3"><dt className="text-texto-2">E-mail</dt><dd><Copiar texto={dados.usuario.email} exibir={dados.usuario.email} /></dd></div>
            <div className="flex justify-between gap-3"><dt className="text-texto-2">Senha inicial</dt><dd><Copiar texto={dados.senha_inicial} exibir={dados.senha_inicial} className="font-mono" /></dd></div>
          </dl>
        )}
        <div className="mt-5 flex justify-end"><Button variante="primario" onClick={aoFechar}>Pronto, já enviei</Button></div>
      </DialogContent>
    </Dialog>
  );
}
