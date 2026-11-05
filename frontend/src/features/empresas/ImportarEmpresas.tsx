import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Download, FileSpreadsheet, Loader2, Upload, Users } from "lucide-react";
import { useRef, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/campos";
import { api, apiForm } from "@/lib/api";
import { useCentral } from "@/lib/buscas";
import { useAtualizarEmpresas, useContabilidade } from "@/lib/empresas";
import { cn } from "@/lib/utils";
import { Painel, Passos } from "./Passos";

interface LinhaPrevia {
  linha: number; cnpj: string; cnpj_formatado: string; razao_social: string | null; apelido: string | null;
  situacao: "criar" | "existente" | "repetida" | "erro"; mensagem: string | null; empresa_id: number | null;
}
interface Previa { linhas: LinhaPrevia[]; resumo: Record<"criar" | "existente" | "repetida" | "erro", number> }
interface LinhaResultado { cnpj_formatado: string; razao_social: string | null; situacao: "criada" | "existente" | "erro"; mensagem: string | null; empresa_id: number | null }
interface Resultado { linhas: LinhaResultado[]; resumo: Record<"criada" | "existente" | "erro", number> }

const SELO = {
  criar: { tom: "ok" as const, texto: "Será criada" },
  existente: { tom: "neutro" as const, texto: "Já cadastrada" },
  repetida: { tom: "alerta" as const, texto: "Repetida" },
  erro: { tom: "erro" as const, texto: "Com erro" },
  criada: { tom: "ok" as const, texto: "Criada" },
};

export function ImportarEmpresas() {
  const { data: contab, isLoading } = useContabilidade();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [filtro, setFiltro] = useState<string>("");
  const entrada = useRef<HTMLInputElement>(null);
  const atualizar = useAtualizarEmpresas();
  const { abrir } = useCentral();

  const ler = useMutation({
    mutationFn: (f: File) => apiForm<Previa>("/api/importacao/empresas/previa", { arquivo: f }),
    onSuccess: (p) => { setPrevia(p); setFiltro(""); },
    onError: () => setPrevia(null),
  });
  const importar = useMutation({
    mutationFn: () => api<Resultado>("/api/importacao/empresas", {
      method: "POST",
      body: JSON.stringify({ linhas: previa!.linhas.filter((l) => l.situacao === "criar").map(({ cnpj, razao_social, apelido }) => ({ cnpj, razao_social, apelido })) }),
    }),
    onSuccess: (r) => {
      setResultado(r);
      atualizar();
      toast.success(`${r.resumo.criada} empresa(s) importada(s). A busca das notas foi agendada.`);
      if (r.resumo.criada) abrir();
    },
  });

  if (isLoading) return <Esqueleto className="h-96 w-full" />;
  if (!contab) return <Navigate to="/contabilidade" replace />;

  const escolher = (f: File | null) => {
    setArquivo(f);
    setPrevia(null);
    setResultado(null);
    if (f) ler.mutate(f);
  };
  const passo = resultado ? 2 : previa ? 1 : 0;
  const linhas = previa?.linhas.filter((l) => !filtro || l.situacao === filtro) ?? [];

  return (
    <div className="max-w-5xl">
      <Cabecalho titulo="Importar empresas por planilha"
        descricao="Todas as empresas importadas usam o certificado da contabilidade (procuração) e já entram na fila de busca." />
      <Passos passos={["Planilha", "Conferir", "Pronto"]} atual={passo} />

      {!resultado && (
        <Painel>
          <div className="flex flex-wrap items-center gap-3">
            <input ref={entrada} type="file" accept=".xlsx,.xlsm,.csv" className="sr-only" aria-label="Planilha de empresas"
              onChange={(e) => escolher(e.target.files?.[0] ?? null)} />
            <button type="button" onClick={() => entrada.current?.click()}
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); escolher(e.dataTransfer.files?.[0] ?? null); }}
              className="flex h-20 flex-1 items-center justify-center gap-3 rounded-xl border-2 border-dashed border-borda-forte bg-fundo px-4 text-sm hover:border-destaque">
              {ler.isPending ? <Loader2 className="size-5 animate-spin text-destaque" /> : arquivo ? <FileSpreadsheet className="size-5 text-destaque" /> : <Upload className="size-5 text-texto-2" />}
              <span className={arquivo ? "font-medium" : "text-texto-2"}>{arquivo ? arquivo.name : "Escolha ou arraste a planilha (.xlsx ou .csv)"}</span>
            </button>
            <Button asChild><a href="/api/importacao/empresas/modelo"><Download /> Baixar modelo</a></Button>
          </div>
          <p className="mt-3 text-xs text-texto-2">
            Colunas: <strong>CNPJ</strong> (obrigatória), <strong>Razão social</strong> e <strong>Apelido</strong>, em qualquer ordem. Sem razão social,
            buscamos na BrasilAPI. CNPJ com os zeros à esquerda apagados pelo Excel é corrigido.
          </p>
          <div className="mt-3">
            <Aviso tom="info">
              <span className="inline-flex items-center gap-1.5"><Users className="size-4" aria-hidden />
                Certificado usado: <strong>{contab.certificado?.titular_nome ?? "—"}</strong>.</span> Cada empresa precisa ter outorgado
              procuração eletrônica no e-CAC a esse titular, com o serviço da <strong>NFS-e</strong>; sem ela, fica como "Procuração pendente".
            </Aviso>
          </div>
          {ler.isError && <div className="mt-3"><Aviso tom="erro">{(ler.error as Error).message}</Aviso></div>}
        </Painel>
      )}

      {previa && !resultado && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {(["", "criar", "existente", "repetida", "erro"] as const).map((k) => (
              <button key={k} onClick={() => setFiltro(k)} aria-pressed={filtro === k}
                className={cn("h-8 rounded-lg border px-2.5", filtro === k ? "border-destaque bg-destaque-suave font-medium text-destaque" : "border-borda bg-superficie text-texto-2 hover:text-texto")}>
                {k === "" ? `Todas (${previa.linhas.length})` : `${SELO[k].texto} (${previa.resumo[k]})`}
              </button>
            ))}
          </div>
          <TabelaLinhas linhas={linhas.map((l) => ({ ...l, chave: l.linha, rotulo: SELO[l.situacao] }))} mostrarLinha />
          {importar.isError && <Aviso tom="erro">{(importar.error as Error).message}</Aviso>}
          <div className="flex items-center justify-between">
            <Button variante="fantasma" onClick={() => escolher(null)}>Trocar planilha</Button>
            <Button variante="primario" disabled={!previa.resumo.criar || importar.isPending} onClick={() => importar.mutate()}>
              {importar.isPending && <Loader2 className="animate-spin" />}
              {previa.resumo.criar ? `Importar ${previa.resumo.criar} empresa(s) por procuração` : "Nenhuma empresa nova para importar"}
            </Button>
          </div>
          {importar.isPending && <p className="text-right text-xs text-texto-2">Linhas sem razão social consultam a BrasilAPI: pode levar alguns segundos.</p>}
        </div>
      )}

      {resultado && (
        <div className="mt-4 space-y-3">
          <Aviso tom={resultado.resumo.erro ? "alerta" : "info"}>
            <span className="inline-flex items-center gap-1.5"><CheckCircle2 className="size-4 text-autorizada" aria-hidden />
              {resultado.resumo.criada} criada(s) · {resultado.resumo.existente} já cadastrada(s) · {resultado.resumo.erro} com erro.</span>{" "}
            As buscas foram agendadas e aparecem na Central de Buscas.
          </Aviso>
          <TabelaLinhas linhas={resultado.linhas.map((l, i) => ({ ...l, chave: i, rotulo: SELO[l.situacao] }))} />
          <div className="flex justify-between">
            <Button variante="fantasma" onClick={() => escolher(null)}>Importar outra planilha</Button>
            <Button variante="primario" asChild><Link to="/empresas">Ver empresas</Link></Button>
          </div>
        </div>
      )}
    </div>
  );
}

function TabelaLinhas({ linhas, mostrarLinha }: {
  linhas: { chave: number; linha?: number; cnpj_formatado: string; razao_social: string | null; apelido?: string | null; mensagem: string | null; empresa_id: number | null; rotulo: { tom: "ok" | "neutro" | "alerta" | "erro"; texto: string } }[];
  mostrarLinha?: boolean;
}) {
  return (
    <div className="max-h-[55vh] overflow-auto rounded-xl border border-borda bg-superficie">
      <table className="w-full text-sm">
        <thead className="sticky top-0 border-b border-borda bg-fundo text-left text-xs text-texto-2">
          <tr>
            {mostrarLinha && <th className="w-14 px-3 py-2 font-medium">Linha</th>}
            <th className="px-3 py-2 font-medium">CNPJ</th>
            <th className="px-3 py-2 font-medium">Razão social</th>
            {mostrarLinha && <th className="px-3 py-2 font-medium">Apelido</th>}
            <th className="px-3 py-2 font-medium">Situação</th>
          </tr>
        </thead>
        <tbody>
          {linhas.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-texto-2">Nenhuma linha neste filtro.</td></tr>}
          {linhas.map((l) => (
            <tr key={l.chave} className="border-b border-borda last:border-0">
              {mostrarLinha && <td className="px-3 py-2 font-mono text-xs text-texto-2">{l.linha}</td>}
              <td className="whitespace-nowrap px-3 py-2 font-mono text-[13px]">{l.cnpj_formatado || "—"}</td>
              <td className="px-3 py-2">{l.razao_social ?? <span className="text-texto-2">—</span>}</td>
              {mostrarLinha && <td className="px-3 py-2 text-texto-2">{l.apelido ?? "—"}</td>}
              <td className="px-3 py-2">
                <Selo tom={l.rotulo.tom} icone={CheckCircle2}>{l.rotulo.texto}</Selo>
                {l.mensagem && <div className="mt-0.5 text-xs text-texto-2">{l.mensagem}</div>}
                {l.empresa_id && l.rotulo.texto !== "Será criada" && (
                  <Link to={`/empresas/${l.empresa_id}?empresa=${l.empresa_id}`} className="text-xs text-destaque hover:underline">Abrir</Link>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
