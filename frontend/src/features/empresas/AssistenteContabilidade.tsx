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
import { useContaEmpresa } from "@/lib/sessao";
import { CertificadoUpload, type CertificadoEscolhido } from "./CertificadoUpload";
import { DADOS_VAZIOS, PassoDados, type DadosEmpresa } from "./PassoDados";
import { LinhaResumo, Painel, Passos } from "./Passos";

/** Primeiro uso (ou renovação): cadastra a contabilidade e o certificado que recebeu as procurações.
 *  Na conta de empresa, é a própria empresa (o único CNPJ da conta) e o e-CNPJ dela. */
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
  const propria = useContaEmpresa();
  const nome = propria ? "a empresa" : "a contabilidade";

  const salvar = useMutation({
    mutationFn: () => apiForm<EmpresaCriada>("/api/contabilidade", { ...dados, arquivo: cert!.arquivo, senha: cert!.senha }),
    onSuccess: (r) => {
      atualizar();
      toast.success(atual ? `Certificado d${nome} atualizado.` : propria ? "Empresa cadastrada." : "Contabilidade cadastrada.");
      r.avisos.forEach((a) => toast.warning(a));
      // Conta de empresa: segue para completar os dados de emissão
      navegar(propria && !atual ? `/emissor/empresas/${r.empresa.id}?empresa=${r.empresa.id}` : propria
        ? `/minha-empresa` : `/empresas?empresa=${r.empresa.id}`);
    },
  });

  const certErrado = cert && cert.info.tipo === "e-CNPJ" && cert.info.titular_doc.slice(0, 8) !== dados.cnpj.slice(0, 8);

  return (
    <div className="max-w-3xl">
      <Cabecalho
        titulo={atual ? `Certificado d${nome}` : "Bem-vindo ao Contask NF"}
        descricao={propria
          ? (atual ? "Atualize os dados ou envie o certificado digital renovado da sua empresa."
            : "Cadastre sua empresa pelo CNPJ e envie o certificado digital (e-CNPJ A1) dela. Com ele, o Contask NF emite as suas notas e traz as que você já emitiu e recebeu.")
          : atual
            ? "Atualize os dados ou envie o certificado renovado. As procurações continuam valendo: elas são dadas ao CNPJ, não ao arquivo."
            : "Primeiro, cadastre a contabilidade e o certificado que recebeu as procurações dos clientes."}
      />
      <Passos passos={[propria ? "Sua empresa" : "Contabilidade", "Certificado", "Confirmar"]} atual={passo} />

      {passo === 0 && (
        <Painel titulo={propria ? "Dados da sua empresa" : "Dados da contabilidade"}>
          <PassoDados inicial={dados} cnpjBloqueado={!!atual} aoContinuar={(d) => { setDados(d); setPasso(1); }} />
        </Painel>
      )}

      {passo === 1 && (
        <Painel
          titulo="Certificado digital"
          descricao={propria
            ? "Use o e-CNPJ A1 da sua empresa (arquivo .pfx ou .p12). Ele assina as notas. O arquivo e a senha são guardados cifrados."
            : "Use o e-CNPJ da contabilidade (ou o e-CPF do titular das procurações). O arquivo e a senha são guardados cifrados."}
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
                Este certificado é de {cert!.info.titular_nome} ({formatarDoc(cert!.info.titular_doc)}), não d{nome}.
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
            <LinhaResumo rotulo={propria ? "Empresa" : "Contabilidade"}>{dados.razao_social}</LinhaResumo>
            <LinhaResumo rotulo="CNPJ"><span className="font-mono">{formatarDoc(dados.cnpj)}</span></LinhaResumo>
            <LinhaResumo rotulo="Certificado">
              <div className="flex items-center gap-2">
                {cert.info.tipo} de {cert.info.titular_nome} <SeloCertificado cert={cert.info} />
              </div>
            </LinhaResumo>
          </dl>
          {!atual && (
            <p className="mt-4 text-sm text-texto-2">
              {propria ? "Ao salvar, a empresa já fica pronta para emitir e a busca das notas dela é agendada."
                : "Ao salvar, a busca das notas da própria contabilidade é agendada."}
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
