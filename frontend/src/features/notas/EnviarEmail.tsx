import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, Loader2, Mail, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Esqueleto, EstadoErro } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { formatarDataHora } from "@/lib/formato";
import { cn } from "@/lib/utils";

/** Nota a enviar: a emitida pelo Contask ("emitida") ou a que veio do ADN ("adn"), em qualquer tela. */
export type AlvoEmail = { origem: "adn" | "emitida"; id: number; rotulo: string } | null;

interface Envio { id: number; para: string; situacao: "enviado" | "erro"; erro: string | null; automatico: boolean; criado_em: string; por: string | null }
interface InfoEnvio { sugestao: string | null; configurado: boolean; limite_destinatarios: number; envios: Envio[] }

const caminho = (a: NonNullable<AlvoEmail>) => (a.origem === "adn" ? `/api/notas/${a.id}/email` : `/api/emissor/notas/${a.id}/email`);
const CLASSE_TEXTO = "w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none hover:border-borda-forte focus-visible:border-destaque focus-visible:ring-2 focus-visible:ring-destaque/25";

/** Envia a NFS-e (DANFSe em PDF + XML) por e-mail pela caixa do sistema e mostra os envios anteriores. */
export function EnviarEmailDialog({ alvo, aoFechar }: { alvo: AlvoEmail; aoFechar: () => void }) {
  const qc = useQueryClient();
  const chave = ["nota-email", alvo?.origem, alvo?.id];
  const info = useQuery({ queryKey: chave, queryFn: () => api<InfoEnvio>(caminho(alvo!)), enabled: !!alvo });
  const [para, setPara] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [tocado, setTocado] = useState(false);
  // Sugestão (e-mail do tomador) entra no campo até a pessoa mexer nele
  useEffect(() => { if (!tocado && info.data?.sugestao) setPara(info.data.sugestao); }, [info.data?.sugestao, tocado]);

  const enviar = useMutation({
    mutationFn: () => api<Envio>(caminho(alvo!), { method: "POST", body: JSON.stringify({ para, mensagem: mensagem.trim() || null }) }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: chave });
      toast.success(`Nota enviada para ${r.para}.`);
      fechar();
    },
    onSettled: () => qc.invalidateQueries({ queryKey: chave }),
  });
  const fechar = () => { setPara(""); setMensagem(""); setTocado(false); enviar.reset(); aoFechar(); };

  return (
    <Dialog open={!!alvo} onOpenChange={(v) => !v && !enviar.isPending && fechar()}>
      <DialogContent titulo="Enviar nota por e-mail"
        descricao={<>{alvo?.rotulo}. Sai do e-mail do Contask NF com o DANFSe (PDF) e o XML em anexo. As respostas vão para o seu e-mail.</>}>
        {info.isLoading && <Esqueleto className="h-40 w-full" />}
        {info.isError && <EstadoErro mensagem={(info.error as Error).message} tentarDeNovo={() => info.refetch()} />}
        {info.data && (
          <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); enviar.mutate(); }}>
            {!info.data.configurado && (
              <Aviso tom="alerta">O e-mail do sistema ainda não está configurado no servidor. O envio fica disponível assim que ele for ligado.</Aviso>
            )}
            <Campo rotulo="Para" obrigatorio ajuda={`Até ${info.data.limite_destinatarios} e-mails, separados por vírgula.`}>
              {(p) => <Input {...p} value={para} maxLength={1200} autoFocus placeholder="financeiro@cliente.com.br"
                onChange={(ev) => { setTocado(true); setPara(ev.target.value); }} required />}
            </Campo>
            <Campo rotulo="Mensagem (opcional)" ajuda="Vai no corpo do e-mail, junto com número, valor e chave de acesso da nota.">
              {(p) => <textarea {...p} rows={3} maxLength={2000} value={mensagem} onChange={(ev) => setMensagem(ev.target.value)} className={CLASSE_TEXTO} />}
            </Campo>
            {enviar.isError && <Aviso tom="erro">{(enviar.error as Error).message}</Aviso>}
            <div className="flex justify-end gap-2">
              <Button type="button" variante="fantasma" onClick={fechar} disabled={enviar.isPending}>Cancelar</Button>
              <Button type="submit" variante="primario" disabled={enviar.isPending || !para.trim() || !info.data.configurado}>
                {enviar.isPending ? <Loader2 className="animate-spin" /> : <Send />} Enviar
              </Button>
            </div>
            <section className="border-t border-borda pt-3">
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium"><Mail className="size-4 text-texto-2" aria-hidden /> Envios desta nota</h3>
              {info.data.envios.length === 0 ? (
                <p className="text-sm text-texto-2">Esta nota ainda não foi enviada por e-mail.</p>
              ) : (
                <ul className="max-h-48 space-y-2 overflow-y-auto">
                  {info.data.envios.map((e) => (
                    <li key={e.id} className="flex gap-2 text-sm">
                      {e.situacao === "enviado"
                        ? <CircleCheck className="mt-0.5 size-4 shrink-0 text-autorizada" aria-label="Enviado" />
                        : <CircleAlert className="mt-0.5 size-4 shrink-0 text-cancelada" aria-label="Não enviado" />}
                      <div className="min-w-0">
                        <div className="break-all">{e.para}</div>
                        <div className={cn("text-xs", e.situacao === "erro" ? "text-cancelada" : "text-texto-2")}>
                          {formatarDataHora(e.criado_em)}
                          {e.automatico ? " · automático (recorrente)" : e.por ? ` · por ${e.por}` : ""}
                          {e.situacao === "erro" && ` · não enviado: ${e.erro}`}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
