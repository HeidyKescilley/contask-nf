import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, Esqueleto } from "@/components/estados";
import { SeloCertificado } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/campos";
import { apiForm, type EmpresaCriada } from "@/lib/api";
import { useAtualizarEmpresas, useContabilidade } from "@/lib/empresas";
import { formatarDoc } from "@/lib/formato";
import { CertificadoUpload, type CertificadoEscolhido } from "./CertificadoUpload";
import { DADOS_VAZIOS, PassoDados, type DadosEmpresa } from "./PassoDados";
import { LinhaResumo, Painel, Passos } from "./Passos";

/** Primeiro uso (ou renovação): cadastra a contabilidade e o certificado que recebeu as procurações. */
export function AssistenteContabilidade() {
  const { data: atual, isLoading } = useContabilidade();
  if (isLoading) return <Esqueleto className="h-96 w-full" />;
  return <Assistente key={atual?.id ?? "nova"} atual={atual ?? null} />;
}

function Assistente({ atual }: { atual: import("@/lib/api").Empresa | null }) {
  const [passo, setPasso] = useState(0);
  const [dados, setDados] = useState<DadosEmpresa>(
    atual
      ? { ...DADOS_VAZIOS, cnpj: atual.cnpj, razao_social: atual.razao_social, nome_fantasia: atual.nome_fantasia ?? "",
          apelido: atual.apelido ?? "", uf: atual.uf ?? "", municipio: atual.municipio ?? "",
          situacao_cadastral: atual.situacao_cadastral ?? "" }
      : DADOS_VAZIOS,
  );
  const [cert, setCert] = useState<CertificadoEscolhido | null>(null);
  const navegar = useNavigate();
  const atualizar = useAtualizarEmpresas();

  const salvar = useMutation({
    mutationFn: () => apiForm<EmpresaCriada>("/api/contabilidade", { ...dados, arquivo: cert!.arquivo, senha: cert!.senha }),
    onSuccess: (r) => {
      atualizar();
      toast.success(atual ? "Certificado da contabilidade atualizado." : "Contabilidade cadastrada.");
      r.avisos.forEach((a) => toast.warning(a));
      navegar(`/empresas?empresa=${r.empresa.id}`);
    },
  });

  const certErrado = cert && cert.info.tipo === "e-CNPJ" && cert.info.titular_doc.slice(0, 8) !== dados.cnpj.slice(0, 8);

  return (
    <div className="max-w-3xl">
      <Cabecalho
        titulo={atual ? "Certificado da contabilidade" : "Bem-vindo ao Contask NF"}
        descricao={atual
          ? "Atualize os dados ou envie o certificado renovado. As procurações continuam valendo: elas são dadas ao CNPJ, não ao arquivo."
          : "Primeiro, cadastre a contabilidade e o certificado que recebeu as procurações dos clientes."}
      />
      <Passos passos={["Contabilidade", "Certificado", "Confirmar"]} atual={passo} />

      {passo === 0 && (
        <Painel titulo="Dados da contabilidade">
          <PassoDados inicial={dados} cnpjBloqueado={!!atual} aoContinuar={(d) => { setDados(d); setPasso(1); }} />
        </Painel>
      )}

      {passo === 1 && (
        <Painel
          titulo="Certificado digital"
          descricao="Use o e-CNPJ da contabilidade (ou o e-CPF do titular das procurações). O arquivo e a senha são guardados cifrados."
        >
          {atual?.certificado && (
            <div className="mb-4 flex items-center justify-between rounded-xl border border-borda bg-fundo px-3.5 py-2.5 text-sm">
              <span className="text-texto-2">Certificado atual: {atual.certificado.titular_nome}</span>
              <SeloCertificado cert={atual.certificado} />
            </div>
          )}
          <CertificadoUpload valor={cert} onChange={setCert} />
          {certErrado && (
            <div className="mt-3">
              <Aviso tom="erro">
                Este certificado é de {cert!.info.titular_nome} ({formatarDoc(cert!.info.titular_doc)}), não da contabilidade.
              </Aviso>
            </div>
          )}
          <div className="mt-5 flex justify-between">
            <Button variante="fantasma" onClick={() => setPasso(0)}>Voltar</Button>
            <Button variante="primario" disabled={!cert || cert.info.situacao === "vencido" || !!certErrado} onClick={() => setPasso(2)}>
              Continuar
            </Button>
          </div>
        </Painel>
      )}

      {passo === 2 && cert && (
        <Painel titulo="Confirmar">
          <dl>
            <LinhaResumo rotulo="Contabilidade">{dados.razao_social}</LinhaResumo>
            <LinhaResumo rotulo="CNPJ"><span className="font-mono">{formatarDoc(dados.cnpj)}</span></LinhaResumo>
            <LinhaResumo rotulo="Certificado">
              <div className="flex items-center gap-2">
                {cert.info.tipo} de {cert.info.titular_nome} <SeloCertificado cert={cert.info} />
              </div>
            </LinhaResumo>
          </dl>
          {!atual && (
            <p className="mt-4 text-sm text-texto-2">
              Ao salvar, a busca das notas da própria contabilidade é agendada.
            </p>
          )}
          {salvar.isError && <div className="mt-4"><Aviso tom="erro">{(salvar.error as Error).message}</Aviso></div>}
          <div className="mt-5 flex justify-between">
            <Button variante="fantasma" onClick={() => setPasso(1)} disabled={salvar.isPending}>Voltar</Button>
            <Button variante="primario" onClick={() => salvar.mutate()} disabled={salvar.isPending}>
              {salvar.isPending && <Loader2 className="animate-spin" />} Salvar
            </Button>
          </div>
        </Painel>
      )}
    </div>
  );
}
