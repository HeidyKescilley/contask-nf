import { useQuery } from "@tanstack/react-query";
import { KeyRound, LayoutDashboard, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { api, type Saude } from "@/lib/api";
import { useSessao, useUso } from "@/lib/sessao";

function useSaude() {
  return useQuery({ queryKey: ["saude"], queryFn: () => api<Saude>("/api/saude") });
}

function IrParaContabilidade() {
  return (
    <Button variante="primario" asChild>
      <Link to="/contabilidade">
        <KeyRound /> Cadastrar a contabilidade
      </Link>
    </Button>
  );
}

/** Sem contabilidade ou sem empresa selecionada (usado pelas páginas que dependem de empresa). */
export function EstadoSemEmpresa({ icone }: { icone: typeof LayoutDashboard }) {
  const saude = useSaude();
  if (saude.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (saude.isError) return <EstadoErro mensagem={(saude.error as Error).message} tentarDeNovo={() => saude.refetch()} />;
  if (!saude.data?.tem_contabilidade)
    return (
      <EstadoVazio icone={icone} titulo="Nenhuma empresa cadastrada" acao={<IrParaContabilidade />}>
        Primeiro uso: cadastre a contabilidade e o certificado dela. Depois, cadastre as empresas pelo CNPJ e a
        busca das notas começa sozinha.
      </EstadoVazio>
    );
  return (
    <EstadoVazio icone={icone} titulo="Nenhuma empresa selecionada"
      acao={<Button variante="primario" asChild><Link to="/empresas/nova"><Plus /> Nova empresa</Link></Button>}>
      Escolha uma empresa no seletor do topo ou cadastre uma nova.
    </EstadoVazio>
  );
}

function Linha({ rotulo, valor, ok }: { rotulo: string; valor: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-borda py-2.5 text-sm last:border-0">
      <span className="text-texto-2">{rotulo}</span>
      <span className="flex items-center gap-2 font-mono text-[13px]">
        {ok !== undefined && (
          <span className={ok ? "text-autorizada" : "text-cancelada"} aria-hidden>
            ●
          </span>
        )}
        {valor}
      </span>
    </div>
  );
}

export function Configuracoes() {
  const { data, isLoading, isError, error, refetch } = useSaude();
  const sessao = useSessao();
  const uso = useUso();
  const online = !!sessao.data?.login_ativo;
  const n = (v: number) => v.toLocaleString("pt-BR");
  return (
    <>
      <Cabecalho titulo="Configurações" descricao="Situação do sistema e uso do plano." />
      <section className="max-w-xl rounded-xl border border-borda bg-superficie px-5 py-2">
        {isLoading && <Esqueleto className="my-3 h-28 w-full" />}
        {isError && <div className="py-3"><EstadoErro mensagem={(error as Error).message} tentarDeNovo={() => refetch()} /></div>}
        {data && (
          <>
            <Linha rotulo="Versão" valor={data.versao} />
            <Linha rotulo="Banco de dados" valor={`SQLite (${data.banco.journal_mode.toUpperCase()})`} ok={data.banco.ok} />
            <Linha
              rotulo={online ? "Chave-mestra dos certificados" : "Chave-mestra (Gerenciador de Credenciais)"}
              valor={data.chave_mestra ? "disponível" : "indisponível"}
              ok={data.chave_mestra}
            />
            <Linha rotulo="Empresas cadastradas" valor={String(data.empresas)} />
            {uso.isError && <Linha rotulo="XMLs novos no mês" valor="não foi possível consultar" ok={false} />}
            {uso.data?.teste && (
              <Linha rotulo="Teste grátis" valor={`${n(uso.data.usados)} de ${n(uso.data.teste.max_xmls)} XMLs`} ok={!uso.data.teste.concluido} />
            )}
            {uso.data && !uso.data.teste && (
              <Linha
                rotulo={`XMLs novos em ${uso.data.mes.slice(5)}/${uso.data.mes.slice(0, 4)}`}
                valor={uso.data.limite ? `${n(uso.data.usados)} de ${n(uso.data.limite)}` : `${n(uso.data.usados)} (sem limite)`}
                ok={uso.data.situacao === "sem_limite" ? undefined : uso.data.situacao !== "atingido"}
              />
            )}
          </>
        )}
      </section>
      {uso.data?.limite && !uso.data.teste && (
        <p className="mt-3 max-w-xl text-xs text-texto-2">
          O limite conta os XMLs (notas e eventos) baixados nas buscas do mês. A carga inicial do histórico de cada empresa não conta.
        </p>
      )}
    </>
  );
}

export function NaoEncontrada() {
  return (
    <EstadoVazio icone={LayoutDashboard} titulo="Página não encontrada" acao={<Button asChild><Link to="/dashboard">Ir para o Dashboard</Link></Button>}>
      O endereço não corresponde a nenhuma tela.
    </EstadoVazio>
  );
}
