import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, LifeBuoy, Loader2, MessageCircle } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Dica } from "@/components/ui/tooltip";
import { api } from "@/lib/api";

const WHATSAPP = "5561996543664";
const CLASSE_TEXTO = "w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none focus:border-destaque focus:ring-2 focus:ring-destaque/20";

/** Botão "Ajuda" do topo: o pedido fica no painel de Monitoramento do suporte. */
export function BotaoSuporte() {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <Dica texto="Ajuda e suporte" lado="bottom">
        <button onClick={() => setAberto(true)} aria-label="Ajuda e suporte"
          className="flex h-9 items-center gap-2 rounded-xl px-3 text-sm text-texto-2 hover:bg-superficie-2 hover:text-texto">
          <LifeBuoy className="size-4" aria-hidden /><span className="hidden md:inline">Ajuda</span>
        </button>
      </Dica>
      <Dialog open={aberto} onOpenChange={setAberto}>
        {aberto && <Formulario fechar={() => setAberto(false)} />}
      </Dialog>
    </>
  );
}

function Formulario({ fechar }: { fechar: () => void }) {
  const local = useLocation();
  const assuntos = useQuery({ queryKey: ["suporte", "assuntos"], queryFn: () => api<{ valor: string; rotulo: string }[]>("/api/uso/suporte/assuntos"), staleTime: Infinity });
  const [assunto, setAssunto] = useState("");
  const [mensagem, setMensagem] = useState("");
  const enviar = useMutation({
    mutationFn: () => api<{ id: number }>("/api/uso/suporte", { method: "POST", body: JSON.stringify({ assunto, mensagem, pagina: local.pathname }) }),
  });
  const texto = encodeURIComponent("Olá! Preciso de ajuda com o Contask NF.");

  if (enviar.isSuccess) {
    return (
      <DialogContent titulo="Pedido enviado">
        <div className="flex flex-col items-center py-2 text-center">
          <CheckCircle2 className="mb-3 size-10 text-autorizada" aria-hidden />
          <p className="text-sm">Recebemos seu pedido nº {enviar.data.id}. Respondemos pelo e-mail ou WhatsApp do seu cadastro.</p>
          <p className="mt-1 text-sm text-texto-2">Se for urgente, chame no WhatsApp.</p>
          <div className="mt-5 flex gap-2">
            <Button asChild><a href={`https://wa.me/${WHATSAPP}?text=${texto}`} target="_blank" rel="noreferrer"><MessageCircle /> Abrir WhatsApp</a></Button>
            <Button variante="primario" onClick={fechar}>Fechar</Button>
          </div>
        </div>
      </DialogContent>
    );
  }
  return (
    <DialogContent titulo="Ajuda e suporte" descricao="Conte o que aconteceu. A tela em que você está vai junto com o pedido.">
      <div className="grid gap-4">
        <Campo rotulo="Assunto" obrigatorio>
          {(p) => (
            <Select {...p} value={assunto} onChange={(e) => setAssunto(e.target.value)} disabled={assuntos.isLoading}>
              <option value="">{assuntos.isLoading ? "Carregando…" : "Escolha o assunto"}</option>
              {assuntos.data?.map((a) => <option key={a.valor} value={a.valor}>{a.rotulo}</option>)}
            </Select>
          )}
        </Campo>
        <Campo rotulo="Mensagem" obrigatorio ajuda="Evite mandar senhas por aqui.">
          {(p) => <textarea {...p} rows={5} maxLength={4000} value={mensagem} onChange={(e) => setMensagem(e.target.value)} className={CLASSE_TEXTO} />}
        </Campo>
        {assuntos.isError && <Aviso tom="erro">Não foi possível carregar os assuntos. Feche e abra de novo.</Aviso>}
        {enviar.isError && <Aviso tom="erro">{(enviar.error as Error).message}</Aviso>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <a href={`https://wa.me/${WHATSAPP}?text=${texto}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm text-destaque hover:underline">
            <MessageCircle className="size-4" aria-hidden /> Prefiro o WhatsApp
          </a>
          <div className="flex gap-2">
            <Button variante="fantasma" onClick={fechar}>Cancelar</Button>
            <Button variante="primario" disabled={!assunto || mensagem.trim().length < 5 || enviar.isPending} onClick={() => enviar.mutate()}>
              {enviar.isPending && <Loader2 className="animate-spin" />} Enviar
            </Button>
          </div>
        </div>
      </div>
    </DialogContent>
  );
}
