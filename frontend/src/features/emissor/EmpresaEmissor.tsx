import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, FileText, KeyRound, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Copiar } from "@/components/Copiar";
import { EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { api } from "@/lib/api";
import {
  OP_SIMPLES, REG_AP_TRIB_SN, REG_ESP_TRIB, apenasDigitos, useAtualizarEmissor, useEmpresaEmissora, useServicos,
  type ConfigPrestador, type EmpresaEmissora, type Servico,
} from "@/lib/emissor";
import { nomeExibicao } from "@/lib/empresas";
import { formatarDoc } from "@/lib/formato";
import { Painel } from "@/features/empresas/Passos";
import { AbasEmissor } from "./Abas";
import { SeloCertEmissor, SeloSituacaoEmissor } from "./EmpresasEmissoras";
import { ServicoDialog } from "./ServicoDialog";

export function EmpresaEmissor() {
  const id = Number(useParams().id);
  const q = useEmpresaEmissora(id);
  return (
    <>
      <Link to="/emissor/empresas" className="mb-3 inline-flex items-center gap-1.5 text-sm text-texto-2 hover:text-texto">
        <ArrowLeft className="size-4" aria-hidden /> Empresas emissoras
      </Link>
      {q.isLoading && <Esqueleto className="h-96 w-full" />}
      {q.isError && <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />}
      {q.data && <Detalhe key={q.data.id} e={q.data} />}
    </>
  );
}

function Detalhe({ e }: { e: EmpresaEmissora }) {
  const atualizar = useAtualizarEmissor();
  const alternar = useMutation({
    mutationFn: () => api("/api/emissor/empresas/emissao", { method: "PUT", body: JSON.stringify({ empresa_ids: [e.id], emite: !e.emite_nfse }) }),
    onSuccess: () => { atualizar(); toast.success(e.emite_nfse ? "A empresa não emite mais pelo Contask." : "A empresa agora emite NFS-e pelo Contask."); },
    onError: (err) => toast.error((err as Error).message),
  });

  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">{nomeExibicao(e)}</h1>
          <SeloSituacaoEmissor e={e} />
        </div>
        <div className="mt-1 flex items-center gap-3 text-sm text-texto-2">
          <Copiar texto={e.cnpj} exibir={formatarDoc(e.cnpj)} /><span>·</span><span>{e.razao_social}</span>
        </div>
      </div>
      <AbasEmissor />

      <Painel>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <label className="flex cursor-pointer items-start gap-3">
            <input type="checkbox" className="mt-0.5 size-4 cursor-pointer accent-destaque" checked={e.emite_nfse}
              disabled={alternar.isPending} onChange={() => alternar.mutate()} />
            <span>
              <span className="block text-sm font-medium">Emite NFS-e pelo Contask</span>
              <span className="block text-sm text-texto-2">A empresa aparece no emissor e pode emitir com os serviços abaixo.</span>
            </span>
          </label>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-texto-2">Certificado:</span> <SeloCertEmissor e={e} />
          </div>
        </div>
        {e.emite_nfse && e.pendencias.length > 0 && (
          <div className="mt-4">
            <Aviso tom="alerta">
              <p className="font-medium">Antes de emitir:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">{e.pendencias.map((p) => <li key={p}>{p}</li>)}</ul>
              {!e.certificado && (
                <Link to={`/empresas/${e.id}?empresa=${e.id}`} className="mt-2 inline-flex items-center gap-1.5 font-medium text-destaque hover:underline">
                  <KeyRound className="size-4" aria-hidden /> Enviar o certificado da empresa
                </Link>
              )}
            </Aviso>
          </div>
        )}
        {e.certificado?.filial && (
          <div className="mt-4"><Aviso tom="info">O certificado é de outro estabelecimento da mesma empresa ({formatarDoc(e.certificado.titular_doc)}). A emissão com certificado da matriz ainda não foi testada.</Aviso></div>
        )}
      </Painel>

      {e.config && <FormPrestador e={e} cfg={e.config} />}
      <ListaServicos empresaId={e.id} />
    </div>
  );
}

function FormPrestador({ e, cfg }: { e: EmpresaEmissora; cfg: ConfigPrestador }) {
  const atualizar = useAtualizarEmissor();
  const inicial = { ...cfg, inscricao_municipal: cfg.inscricao_municipal ?? "", reg_ap_trib_sn: cfg.reg_ap_trib_sn ?? "", proximo_numero: String(cfg.proximo_numero) };
  const [d, setD] = useState(inicial);
  const mudou = JSON.stringify(d) !== JSON.stringify(inicial);
  const salvar = useMutation({
    mutationFn: () => api<EmpresaEmissora>(`/api/emissor/empresas/${e.id}/config`, {
      method: "PUT",
      body: JSON.stringify({ ...d, reg_ap_trib_sn: d.op_simples === "3" ? d.reg_ap_trib_sn || null : null, proximo_numero: Number(d.proximo_numero) || 0 }),
    }),
    onSuccess: () => { atualizar(); toast.success("Dados do prestador salvos."); },
  });

  return (
    <Painel titulo="Dados do prestador" descricao="Vão em toda nota desta empresa. O regime veio da consulta do CNPJ: confira antes de emitir.">
      <form className="grid grid-cols-2 gap-4" onSubmit={(ev) => { ev.preventDefault(); salvar.mutate(); }}>
        <Campo rotulo="Situação no Simples Nacional" obrigatorio>
          {(p) => (
            <Select {...p} value={d.op_simples} onChange={(ev) => setD({ ...d, op_simples: ev.target.value as ConfigPrestador["op_simples"], reg_ap_trib_sn: ev.target.value === "3" ? d.reg_ap_trib_sn || "1" : "" })}>
              {Object.entries(OP_SIMPLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          )}
        </Campo>
        <Campo rotulo="Regime de apuração (Simples)" obrigatorio={d.op_simples === "3"} ajuda={d.op_simples !== "3" ? "Só para ME/EPP optante." : undefined}>
          {(p) => (
            <Select {...p} value={d.reg_ap_trib_sn} disabled={d.op_simples !== "3"} onChange={(ev) => setD({ ...d, reg_ap_trib_sn: ev.target.value as typeof d.reg_ap_trib_sn })}>
              {d.op_simples !== "3" && <option value="">—</option>}
              {Object.entries(REG_AP_TRIB_SN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          )}
        </Campo>
        <Campo rotulo="Regime especial de tributação">
          {(p) => (
            <Select {...p} value={d.reg_esp_trib} onChange={(ev) => setD({ ...d, reg_esp_trib: ev.target.value })}>
              {Object.entries(REG_ESP_TRIB).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          )}
        </Campo>
        <Campo rotulo="Inscrição municipal" ajuda="Só preencha se o município tiver a inscrição no cadastro nacional (CNC). Informar sem ter gera recusa (E0120).">
          {(p) => <Input {...p} value={d.inscricao_municipal} maxLength={15} onChange={(ev) => setD({ ...d, inscricao_municipal: ev.target.value })} />}
        </Campo>
        <Campo rotulo="Série da DPS" ajuda="De 1 a 49999. Use outra série se a empresa já emite por outro sistema.">
          {(p) => <Input {...p} value={d.serie} inputMode="numeric" maxLength={5} onChange={(ev) => setD({ ...d, serie: apenasDigitos(ev.target.value) })} />}
        </Campo>
        <Campo rotulo="Próximo número da DPS" ajuda="Só mude se souber o último número usado nesta série.">
          {(p) => <Input {...p} value={d.proximo_numero} inputMode="numeric" onChange={(ev) => setD({ ...d, proximo_numero: apenasDigitos(ev.target.value) })} />}
        </Campo>
        {salvar.isError && <div className="col-span-2"><Aviso tom="erro">{(salvar.error as Error).message}</Aviso></div>}
        <div className="col-span-2 flex justify-end gap-2">
          {mudou && <Button type="button" variante="fantasma" onClick={() => setD(inicial)}>Desfazer</Button>}
          <Button type="submit" variante="primario" disabled={!mudou || salvar.isPending}>
            {salvar.isPending && <Loader2 className="animate-spin" />} Salvar
          </Button>
        </div>
      </form>
    </Painel>
  );
}

function ListaServicos({ empresaId }: { empresaId: number }) {
  const [inativos, setInativos] = useState(false);
  const lista = useServicos(empresaId, inativos);
  const atualizar = useAtualizarEmissor();
  const [dialogo, setDialogo] = useState<{ aberto: boolean; servico: Servico | null }>({ aberto: false, servico: null });
  const excluir = useMutation({
    mutationFn: (s: Servico) => api<void>(`/api/emissor/servicos/${s.id}`, { method: "DELETE" }),
    onSuccess: () => { atualizar(); toast.success("Serviço excluído."); },
    onError: (err) => toast.error((err as Error).message),
  });

  return (
    <Painel>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold">Serviços</h2>
          <p className="mt-1 text-sm text-texto-2">Descrição e códigos de cada serviço que a empresa presta.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-texto-2">
            <input type="checkbox" className="size-4 accent-destaque" checked={inativos} onChange={(ev) => setInativos(ev.target.checked)} />
            Mostrar inativos
          </label>
          <Button variante="primario" onClick={() => setDialogo({ aberto: true, servico: null })}><Plus /> Novo serviço</Button>
        </div>
      </div>

      {lista.isLoading && <Esqueleto className="h-24 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data?.length === 0 && (
        <EstadoVazio icone={FileText} titulo="Nenhum serviço cadastrado"
          acao={<Button variante="primario" onClick={() => setDialogo({ aberto: true, servico: null })}><Plus /> Cadastrar o primeiro serviço</Button>}>
          Cadastre a descrição e os códigos uma vez. Nas próximas notas, é só escolher o serviço.
        </EstadoVazio>
      )}
      {lista.data && lista.data.length > 0 && (
        <ul className="divide-y divide-borda rounded-xl border border-borda">
          {lista.data.map((s) => (
            <li key={s.id} className={`flex items-start gap-4 px-4 py-3 ${s.ativo ? "" : "opacity-60"}`}>
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 text-sm font-medium">{s.descricao}{!s.ativo && <span className="ml-2 text-xs font-normal text-texto-2">(inativo)</span>}</p>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-texto-2">
                  <span title={s.ctribnac_descricao ?? undefined}>Item <span className="font-mono">{s.ctribnac_formatado}</span> · {s.ctribnac_descricao}</span>
                  <span title={s.cnbs_descricao ?? undefined}>NBS <span className="font-mono">{s.cnbs_formatado}</span></span>
                  {s.ctribmun && <span>Municipal <span className="font-mono">{s.ctribmun}</span></span>}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button tamanho="icone" variante="fantasma" aria-label="Editar serviço" onClick={() => setDialogo({ aberto: true, servico: s })}><Pencil /></Button>
                <Button tamanho="icone" variante="fantasma" aria-label="Excluir serviço" disabled={excluir.isPending}
                  onClick={() => { if (window.confirm(`Excluir o serviço "${s.descricao.slice(0, 60)}"?`)) excluir.mutate(s); }}><Trash2 /></Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ServicoDialog empresaId={empresaId} servico={dialogo.servico} aberto={dialogo.aberto} aoFechar={() => setDialogo({ aberto: false, servico: null })} />
    </Painel>
  );
}
