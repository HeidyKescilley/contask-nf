import { useMutation } from "@tanstack/react-query";
import { Building, KeyRound, Loader2, Users } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, Esqueleto } from "@/components/estados";
import { SeloCertificado } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/campos";
import { apiForm, type Empresa, type EmpresaCriada } from "@/lib/api";
import { useCentral } from "@/lib/buscas";
import { useAtualizarEmpresas, useContabilidade } from "@/lib/empresas";
import { formatarDoc } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { CertificadoUpload, type CertificadoEscolhido } from "./CertificadoUpload";
import { DADOS_VAZIOS, PassoDados, type DadosEmpresa } from "./PassoDados";
import { LinhaResumo, Painel, Passos } from "./Passos";

export type Modo = "contabilidade" | "proprio";

export function OpcaoCertificado({ ativo, onClick, icone: Icone, titulo, children }: {
  ativo: boolean; onClick: () => void; icone: typeof Users; titulo: string; children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={ativo}
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-colors duration-150",
        ativo ? "border-destaque bg-destaque-suave/50 ring-1 ring-destaque" : "border-borda hover:border-borda-forte",
      )}
    >
      <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg", ativo ? "bg-destaque text-destaque-texto" : "bg-superficie-2 text-texto-2")}>
        <Icone className="size-4" aria-hidden />
      </span>
      <span className="flex-1">
        <span className="block text-sm font-medium">{titulo}</span>
        <span className="mt-1 block text-sm text-texto-2">{children}</span>
      </span>
    </button>
  );
}

/** Bloco de escolha do certificado, usado no cadastro e na troca de certificado. */
export function EscolhaCertificado({ contab, cnpj, modo, setModo, cert, setCert }: {
  contab: Empresa | null; cnpj: string; modo: Modo; setModo: (m: Modo) => void;
  cert: CertificadoEscolhido | null; setCert: (c: CertificadoEscolhido | null) => void;
}) {
  return (
    <div className="space-y-3" role="radiogroup" aria-label="Certificado usado na busca">
      <OpcaoCertificado ativo={modo === "contabilidade"} onClick={() => setModo("contabilidade")} icone={Users}
        titulo="Certificado da contabilidade (procuração)">
        {contab?.certificado ? (
          <span className="flex flex-wrap items-center gap-2">
            {contab.certificado.titular_nome} · {formatarDoc(contab.certificado.titular_doc)}
            <SeloCertificado cert={contab.certificado} />
          </span>
        ) : "A contabilidade ainda não tem certificado."}
      </OpcaoCertificado>
      {modo === "contabilidade" && (
        <Aviso tom="info">
          A empresa precisa ter outorgado procuração eletrônica no e-CAC a{" "}
          <strong>{contab?.certificado?.titular_nome ?? "titular do certificado"}</strong>, incluindo o serviço da{" "}
          <strong>NFS-e</strong>. Sem ela, a busca fica como "Procuração pendente".
        </Aviso>
      )}
      <OpcaoCertificado ativo={modo === "proprio"} onClick={() => setModo("proprio")} icone={KeyRound}
        titulo="Certificado da própria empresa">
        Envie o e-CNPJ da empresa (.pfx) e a senha.
      </OpcaoCertificado>
      {modo === "proprio" && <div className="pl-1 pt-1"><CertificadoUpload cnpjEmpresa={cnpj} valor={cert} onChange={setCert} /></div>}
    </div>
  );
}

export function NovaEmpresa() {
  const { data: contab, isLoading } = useContabilidade();
  const [passo, setPasso] = useState(0);
  const [dados, setDados] = useState<DadosEmpresa>(DADOS_VAZIOS);
  const [modo, setModo] = useState<Modo>("contabilidade");
  const [cert, setCert] = useState<CertificadoEscolhido | null>(null);
  const navegar = useNavigate();
  const atualizar = useAtualizarEmpresas();
  const { abrir: abrirCentral } = useCentral();

  const salvar = useMutation({
    mutationFn: () => apiForm<EmpresaCriada>("/api/empresas", {
      ...dados, modo_certificado: modo, ...(modo === "proprio" && cert ? { arquivo: cert.arquivo, senha: cert.senha } : {}),
    }),
    onSuccess: (r) => {
      atualizar();
      toast.success("Empresa cadastrada. A busca das notas foi agendada.");
      r.avisos.forEach((a) => toast.warning(a));
      navegar(`/dashboard?empresa=${r.empresa.id}`);
      abrirCentral(r.empresa.id);
    },
  });

  if (isLoading) return <Esqueleto className="h-96 w-full" />;
  if (!contab) return <Navigate to="/contabilidade" replace />;

  const certOk = modo === "contabilidade" ? !!contab.certificado : !!cert && cert.info.situacao !== "vencido";

  return (
    <div className="max-w-3xl">
      <Cabecalho titulo="Nova empresa" descricao="Cadastre pelo CNPJ. A busca de todo o histórico de NFS-e começa ao confirmar." />
      <Passos passos={["Dados", "Certificado", "Confirmar"]} atual={passo} />

      {passo === 0 && (
        <Painel titulo="Dados da empresa">
          <PassoDados inicial={dados} aoContinuar={(d) => { setDados(d); setPasso(1); }} />
        </Painel>
      )}

      {passo === 1 && (
        <Painel titulo="Certificado usado na busca">
          <EscolhaCertificado contab={contab} cnpj={dados.cnpj} modo={modo} setModo={setModo} cert={cert} setCert={setCert} />
          <div className="mt-5 flex justify-between">
            <Button variante="fantasma" onClick={() => setPasso(0)}>Voltar</Button>
            <Button variante="primario" disabled={!certOk} onClick={() => setPasso(2)}>Continuar</Button>
          </div>
        </Painel>
      )}

      {passo === 2 && (
        <Painel titulo="Confirmar">
          <dl>
            <LinhaResumo rotulo="Empresa">
              <div className="flex items-center gap-2"><Building className="size-4 text-texto-2" aria-hidden />{dados.razao_social}</div>
            </LinhaResumo>
            <LinhaResumo rotulo="CNPJ"><span className="font-mono">{formatarDoc(dados.cnpj)}</span></LinhaResumo>
            {dados.apelido && <LinhaResumo rotulo="Apelido">{dados.apelido}</LinhaResumo>}
            <LinhaResumo rotulo="Local">{[dados.municipio, dados.uf].filter(Boolean).join(" / ") || "—"}</LinhaResumo>
            <LinhaResumo rotulo="Situação cadastral">{dados.situacao_cadastral || "Não informada"}</LinhaResumo>
            <LinhaResumo rotulo="Certificado">
              {modo === "contabilidade"
                ? `Da contabilidade, por procuração (${contab.certificado?.titular_nome})`
                : `Próprio: ${cert?.info.titular_nome}`}
            </LinhaResumo>
          </dl>
          {salvar.isError && <div className="mt-4"><Aviso tom="erro">{(salvar.error as Error).message}</Aviso></div>}
          <div className="mt-5 flex justify-between">
            <Button variante="fantasma" onClick={() => setPasso(1)} disabled={salvar.isPending}>Voltar</Button>
            <Button variante="primario" onClick={() => salvar.mutate()} disabled={salvar.isPending}>
              {salvar.isPending && <Loader2 className="animate-spin" />} Cadastrar e iniciar busca
            </Button>
          </div>
        </Painel>
      )}
    </div>
  );
}
