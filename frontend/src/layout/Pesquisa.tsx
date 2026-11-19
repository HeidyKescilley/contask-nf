import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const DECEPCAO = [
  { valor: "muito", rotulo: "Muito chateado" },
  { valor: "pouco", rotulo: "Um pouco chateado" },
  { valor: "nada", rotulo: "Não ficaria chateado" },
] as const;
const CLASSE_TEXTO = "w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none focus:border-destaque focus:ring-2 focus:ring-destaque/20";

/** Pesquisa curta: aparece depois de 7 dias de conta e 3 dias de uso (regra no servidor), uma vez a cada 90 dias. */
export function PesquisaNoApp() {
  const pendente = useQuery({ queryKey: ["uso", "pesquisa"], queryFn: () => api<{ mostrar: boolean }>("/api/uso/pesquisa"), staleTime: Infinity, retry: false });
  const [aberta, setAberta] = useState(false);
  const [decepcao, setDecepcao] = useState<string | null>(null);
  const [nps, setNps] = useState<number | null>(null);
  const [horas, setHoras] = useState("");
  const [comentario, setComentario] = useState("");

  useEffect(() => {
    if (!pendente.data?.mostrar) return;
    const t = window.setTimeout(() => setAberta(true), 20_000); // não interrompe quem acabou de entrar
    return () => clearTimeout(t);
  }, [pendente.data?.mostrar]);

  const responder = useMutation({
    mutationFn: (adiada: boolean) => api("/api/uso/pesquisa", { method: "POST", body: JSON.stringify(adiada ? { adiada: true }
      : { decepcao, nps, horas: horas ? Number(horas) : null, comentario: comentario.trim() || null }) }),
    onSuccess: () => setAberta(false),
  });

  return (
    <Dialog open={aberta} onOpenChange={(v) => { if (!v && !responder.isPending) responder.mutate(true); }}>
      {aberta && (
        <DialogContent titulo="Ajude a melhorar o Contask NF" descricao="São 3 perguntas rápidas. As respostas vão só para a equipe do Contask.">
          <div className="grid gap-5">
            <fieldset>
              <legend className="mb-2 text-sm font-medium">Como você se sentiria se o Contask NF deixasse de existir?</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {DECEPCAO.map((d) => (
                  <button key={d.valor} type="button" onClick={() => setDecepcao(d.valor)} aria-pressed={decepcao === d.valor}
                    className={cn("rounded-xl border px-3 py-2 text-sm transition-colors", decepcao === d.valor
                      ? "border-destaque bg-destaque-suave text-texto" : "border-borda hover:bg-superficie-2")}>{d.rotulo}</button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="mb-2 text-sm font-medium">De 0 a 10, quanto você recomendaria o Contask NF a um colega?</legend>
              <div className="grid grid-cols-11 gap-1">
                {Array.from({ length: 11 }, (_, i) => (
                  <button key={i} type="button" onClick={() => setNps(i)} aria-pressed={nps === i} aria-label={`Nota ${i}`}
                    className={cn("h-9 rounded-lg border font-mono text-sm tabular-nums transition-colors", nps === i
                      ? "border-destaque bg-destaque text-destaque-texto" : "border-borda hover:bg-superficie-2")}>{i}</button>
                ))}
              </div>
              <div className="mt-1 flex justify-between text-xs text-texto-2"><span>Nada provável</span><span>Muito provável</span></div>
            </fieldset>
            <Campo rotulo="Quantas horas por mês o Contask NF economiza para você? (aproximado)">
              {(p) => <Input {...p} type="number" min={0} max={744} inputMode="numeric" value={horas} onChange={(e) => setHoras(e.target.value)} className="w-32" />}
            </Campo>
            <Campo rotulo="Quer contar mais alguma coisa? (opcional)">
              {(p) => <textarea {...p} rows={2} maxLength={2000} value={comentario} onChange={(e) => setComentario(e.target.value)} className={CLASSE_TEXTO} />}
            </Campo>
            {responder.isError && <Aviso tom="erro">{(responder.error as Error).message}</Aviso>}
            <div className="flex justify-end gap-2">
              <Button variante="fantasma" disabled={responder.isPending} onClick={() => responder.mutate(true)}>Responder depois</Button>
              <Button variante="primario" disabled={(decepcao === null && nps === null) || responder.isPending} onClick={() => responder.mutate(false)}>
                {responder.isPending && <Loader2 className="animate-spin" />} Enviar
              </Button>
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
