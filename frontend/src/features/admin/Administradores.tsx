import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, KeyRound, Loader2, ShieldCheck, ShieldOff, UserCog, UserPlus, UserRound, UserRoundCheck, UserRoundX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { formatarDataHora } from "@/lib/formato";
import { useSessaoAdmin } from "@/lib/sessaoAdmin";
import { cn } from "@/lib/utils";
import { type ComSenha, SenhaInicial, type UsuarioAdm } from "./Administracao";

interface Administrador extends UsuarioAdm {
  /** sem escritório: só entra na administração */
  so_administracao: boolean;
  /** nome do escritório de quem também usa o sistema */
  escritorio: string | null;
}

const CHAVE = ["admin", "administradores"];

/** Quem entra na administração: usuários só dela e quem também usa o sistema (ex.: a CONTELB). */
export function Administradores() {
  const sessao = useSessaoAdmin();
  const eu = sessao.data?.usuario?.id;
  const lista = useQuery({ queryKey: CHAVE, queryFn: () => api<Administrador[]>("/api/admin/administradores"), enabled: !!eu });
  const [novo, setNovo] = useState(false);
  const [senha, setSenha] = useState<ComSenha | null>(null);

  return (
    <>
      <Cabecalho titulo="Administradores"
        descricao="Quem entra na administração. O usuário criado aqui é só da administração: não entra no sistema nem vê empresas e notas."
        acoes={<Button variante="primario" onClick={() => setNovo(true)}><UserPlus /> Novo administrador</Button>} />
      {lista.isLoading && <Esqueleto className="h-48 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data?.length === 0 && (
        <EstadoVazio icone={UserCog} titulo="Nenhum administrador">Crie o primeiro usuário da administração.</EstadoVazio>
      )}
      {!!lista.data?.length && (
        <ul className="divide-y divide-borda rounded-2xl border border-borda bg-superficie">
          {lista.data.map((u) => <Linha key={u.id} u={u} eu={u.id === eu} aoSenha={setSenha} />)}
        </ul>
      )}
      <NovoAdministrador aberto={novo} aoFechar={() => setNovo(false)} aoCriar={setSenha} />
      <SenhaInicial dados={senha} aoFechar={() => setSenha(null)} caminho="/admin" />
    </>
  );
}

function Linha({ u, eu, aoSenha }: { u: Administrador; eu: boolean; aoSenha: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const atualizar = () => {
    qc.invalidateQueries({ queryKey: CHAVE });
    qc.invalidateQueries({ queryKey: ["admin", "escritorios"] });
  };
  const erro = (e: unknown) => toast.error((e as Error).message);
  const senha = useMutation({
    mutationFn: () => api<ComSenha>(`/api/admin/usuarios/${u.id}/senha`, { method: "POST" }),
    onSuccess: (r) => { atualizar(); aoSenha(r); },
    onError: erro,
  });
  const ativo = useMutation({
    mutationFn: () => api<UsuarioAdm>(`/api/admin/usuarios/${u.id}/ativo`, { method: "PUT", body: JSON.stringify({ ativo: !u.ativo }) }),
    onSuccess: (r) => { atualizar(); toast.success(r.ativo ? "Acesso reativado." : "Acesso desativado: a pessoa saiu da administração."); },
    onError: erro,
  });
  const remover = useMutation({
    mutationFn: () => api<UsuarioAdm>(`/api/admin/administradores/${u.id}`, { method: "DELETE" }),
    onSuccess: () => { atualizar(); toast.success("Acesso à administração retirado. O acesso ao sistema continua."); },
    onError: erro,
  });
  const ocupado = senha.isPending || ativo.isPending || remover.isPending;
  return (
    <li className={cn("flex flex-wrap items-center gap-3 px-4 py-3", !u.ativo && "opacity-60")}>
      <div className="w-full min-w-0 sm:w-auto sm:flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <span className="truncate">{u.nome || u.email}</span>
          {eu && <Selo tom="destaque" icone={UserRound}>Você</Selo>}
          {u.so_administracao
            ? <Selo tom="neutro" icone={ShieldCheck}>Só administração</Selo>
            : <Selo tom="neutro" icone={Building2}>Também usa o sistema</Selo>}
          {!u.ativo && <Selo tom="erro" icone={UserRoundX}>Desativado</Selo>}
          {u.ativo && u.trocar_senha && <Selo tom="alerta" icone={KeyRound}>Senha inicial</Selo>}
        </p>
        <p className="mt-0.5 break-words text-xs text-texto-2">
          {u.email}{u.escritorio ? ` · escritório: ${u.escritorio}` : ""} · último acesso: {u.ultimo_acesso_em ? formatarDataHora(u.ultimo_acesso_em) : "nunca"}
        </p>
      </div>
      {!eu && (
        <div className="flex flex-wrap gap-1">
          {u.so_administracao && (
            <Button tamanho="pequeno" variante="fantasma" disabled={ocupado}
              onClick={() => { if (window.confirm(`Gerar nova senha inicial para ${u.email}? A atual deixa de valer.`)) senha.mutate(); }}>
              {senha.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Nova senha
            </Button>
          )}
          {u.so_administracao ? (
            <Button tamanho="pequeno" variante="fantasma" disabled={ocupado}
              onClick={() => { if (u.ativo ? window.confirm(`Desativar o acesso de ${u.email} à administração?`) : true) ativo.mutate(); }}>
              {ativo.isPending ? <Loader2 className="animate-spin" /> : u.ativo ? <UserRoundX /> : <UserRoundCheck />} {u.ativo ? "Desativar" : "Reativar"}
            </Button>
          ) : (
            <Button tamanho="pequeno" variante="fantasma" disabled={ocupado}
              onClick={() => { if (window.confirm(`Tirar o acesso de ${u.email} à administração? O acesso ao sistema continua.`)) remover.mutate(); }}>
              {remover.isPending ? <Loader2 className="animate-spin" /> : <ShieldOff />} Tirar da administração
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

function NovoAdministrador({ aberto, aoFechar, aoCriar }: { aberto: boolean; aoFechar: () => void; aoCriar: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const criar = useMutation({
    mutationFn: () => api<ComSenha>("/api/admin/administradores", { method: "POST", body: JSON.stringify({ email, nome }) }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: CHAVE }); fechar(); aoCriar(r); },
  });
  const fechar = () => { setEmail(""); setNome(""); criar.reset(); aoFechar(); };
  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && !criar.isPending && fechar()}>
      <DialogContent titulo="Novo administrador"
        descricao="Acesso só à administração (Clientes, Leads, Acessos do site, Monitoramento e Administradores). A pessoa troca a senha inicial no primeiro acesso.">
        <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); criar.mutate(); }}>
          <Campo rotulo="Nome">{(a) => <Input {...a} value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />}</Campo>
          <Campo rotulo="E-mail" obrigatorio ajuda="Precisa ser diferente do e-mail usado no sistema.">
            {(a) => <Input {...a} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}
          </Campo>
          {criar.isError && <Aviso tom="erro">{(criar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={criar.isPending}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={criar.isPending || !email}>
              {criar.isPending && <Loader2 className="animate-spin" />} Criar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
