/**
 * Monitoramento do uso (painel do administrador). Tudo vai só para o nosso servidor (/api/uso).
 *
 * Privacidade: nenhum texto da tela sai do navegador. A gravação (rrweb) troca todo texto por asteriscos
 * e mascara todo campo; imagens e canvas ficam bloqueados. No clique, o rótulo só é guardado quando é de
 * botão, link ou aba (até 30 caracteres, sem números) e fora de tabelas, listas de opções e de áreas
 * marcadas com data-privado.
 */

type Evento = { tipo: "pagina" | "tempo" | "clique" | "rolagem" | "erro" | "acao"; nome: string; momento: string; dados?: Record<string, unknown> };

const INTERVALO_ENVIO = 10_000;
const INTERVALO_TEMPO = 15_000;
const ATIVO_ATE = 60_000; // sem interação por 1 min: o tempo para de contar

function novoId() {
  const a = new Uint8Array(12);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

function idDaAba(): string {
  try {
    const salvo = sessionStorage.getItem("contask:aba");
    if (salvo) return salvo;
    const novo = novoId();
    sessionStorage.setItem("contask:aba", novo);
    return novo;
  } catch {
    return novoId();
  }
}

/** /empresas/123 -> /empresas/:id (o servidor normaliza de novo). */
export function rotaNormalizada(caminho: string) {
  return caminho.split("?")[0].replace(/\/\d+(?=\/|$)/g, "/:id") || "/";
}

const INTERATIVO = "a,button,input,select,textarea,label,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=option],[role=checkbox],[role=switch],[role=radio],[tabindex]:not([tabindex='-1'])";
const PRIVADO = "tr,td,th,[role=option],[role=listbox],[data-privado]";

function rotulo(el: Element | null): string {
  if (!el) return "?";
  const tag = el.tagName.toLowerCase();
  const aria = el.getAttribute("aria-label") || el.getAttribute("title");
  const papel = el.getAttribute("role");
  const limpo = (t: string) => t.replace(/\s+/g, " ").trim();
  const seguro = (t: string) => t.length > 0 && t.length <= 30 && !/\d/.test(t);
  if (!el.closest(PRIVADO)) {
    if (aria && seguro(limpo(aria))) return limpo(aria);
    if (["button", "a"].includes(tag) || ["tab", "menuitem", "button", "link"].includes(papel ?? "")) {
      const t = limpo(el.textContent ?? "");
      if (seguro(t)) return t;
    }
  }
  return papel ? `${tag}[${papel}]` : tag;
}

class Monitor {
  private fila: Evento[] = [];
  private gravacao: unknown[] = [];
  private aba = idDaAba();
  private rota = rotaNormalizada(location.pathname);
  private ultimaInteracao = Date.now();
  private maiorRolagem = 0;
  private timers: number[] = [];
  private pararGravacao: (() => void) | null = null;
  private ligado = false;

  iniciar(gravar: boolean) {
    if (this.ligado) return;
    this.ligado = true;
    const marcar = () => { this.ultimaInteracao = Date.now(); };
    for (const ev of ["pointerdown", "keydown", "scroll", "pointermove"]) addEventListener(ev, marcar, { passive: true, capture: true });
    document.addEventListener("click", (e) => this.clique(e), { capture: true });
    addEventListener("scroll", () => this.rolou(), { passive: true });
    addEventListener("error", (e) => this.erro("js", e.message || "Erro de script"));
    addEventListener("unhandledrejection", (e) => {
      const r = e.reason as { message?: string; status?: number } | undefined;
      if (r && typeof r.status === "number") return; // erros da API já são tratados pelo evento contask:erro-api
      this.erro("js", r?.message ?? "Promessa rejeitada");
    });
    addEventListener("contask:erro-api", (e) => {
      const d = (e as CustomEvent<{ status: number; caminho: string }>).detail;
      this.erro("api", `Erro ${d.status || "de conexão"} em ${rotaNormalizada(d.caminho)}`, d.status);
    });
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") this.enviar(true); });
    addEventListener("pagehide", () => this.enviar(true));
    this.timers.push(window.setInterval(() => this.contarTempo(), INTERVALO_TEMPO));
    this.timers.push(window.setInterval(() => this.enviar(false), INTERVALO_ENVIO));
    this.pagina(location.pathname);
    if (gravar) void this.gravar();
  }

  /** Chamado a cada troca de rota (Estrutura). */
  pagina(caminho: string) {
    const rota = rotaNormalizada(caminho);
    if (this.ligado && rota === this.rota && this.fila.some((e) => e.tipo === "pagina")) return;
    this.fecharRolagem();
    this.rota = rota;
    this.maiorRolagem = 0;
    this.rolou();
    this.push("pagina", rota);
  }

  acao(nome: string, dados?: Record<string, unknown>) {
    this.push("acao", nome, dados);
  }

  private push(tipo: Evento["tipo"], nome: string, dados?: Record<string, unknown>) {
    if (!this.ligado) return;
    this.fila.push({ tipo, nome, momento: new Date().toISOString(), dados });
    if (this.fila.length >= 150) this.enviar(false);
  }

  private contarTempo() {
    if (document.visibilityState === "visible" && Date.now() - this.ultimaInteracao < ATIVO_ATE)
      this.push("tempo", this.rota, { s: INTERVALO_TEMPO / 1000 });
  }

  private rolou() {
    const doc = document.documentElement;
    const p = doc.scrollHeight <= innerHeight ? 100 : Math.min(100, Math.round(((scrollY + innerHeight) / doc.scrollHeight) * 100));
    if (p > this.maiorRolagem) this.maiorRolagem = p;
  }

  private fecharRolagem() {
    if (this.ligado && this.maiorRolagem > 0) this.push("rolagem", this.rota, { p: this.maiorRolagem });
  }

  private clique(e: MouseEvent) {
    const alvo = e.target instanceof Element ? e.target : null;
    if (!alvo) return;
    const interativo = alvo.closest(INTERATIVO);
    const doc = document.documentElement;
    const base = { x: e.pageX / Math.max(1, doc.scrollWidth), y: e.pageY, w: innerWidth, h: doc.scrollHeight, alvo: rotulo(interativo ?? alvo) };
    const rota = this.rota;
    if (interativo || getComputedStyle(alvo).cursor === "pointer") {
      this.push("clique", rota, { ...base, morto: false });
      return;
    }
    // Clique em algo que não é botão: "sem resposta" se nada mudar na tela em 800 ms
    let mudou = false;
    const obs = new MutationObserver(() => { mudou = true; });
    obs.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    const antes = location.href;
    window.setTimeout(() => {
      obs.disconnect();
      this.push("clique", rota, { ...base, morto: !mudou && location.href === antes });
    }, 800);
  }

  private erro(nome: string, msg: string, status?: number) {
    this.push("erro", nome, { msg: msg.replace(/\d{6,}/g, "#").slice(0, 300), rota: this.rota, status });
  }

  private async gravar() {
    try {
      const { record } = await import("rrweb");
      const parar = record({
        emit: (ev) => {
          this.gravacao.push(ev);
          if (this.gravacao.length >= 2000) this.enviarGravacao(false);
        },
        maskAllInputs: true,
        maskTextSelector: "*",
        blockSelector: "img,svg image,canvas,video,iframe,[data-bloquear-gravacao]",
        recordCanvas: false,
        collectFonts: false,
        inlineImages: false,
        slimDOMOptions: "all",
        sampling: { mousemove: 100, scroll: 200, input: "last", media: 800 },
        checkoutEveryNms: 10 * 60_000,
      });
      this.pararGravacao = parar ?? null;
      // o retrato inicial da tela é grande (passa do limite de envio ao sair): manda logo
      window.setTimeout(() => this.enviarGravacao(false), 2000);
    } catch {
      /* sem gravação: o resto do monitoramento continua */
    }
  }

  private mandar(url: string, corpo: unknown, aoSair: boolean) {
    const body = JSON.stringify(corpo);
    // keepalive tem limite de 64 KB: só usa ao sair da página
    void fetch(url, { method: "POST", body, keepalive: aoSair && body.length < 60_000, credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" } }).catch(() => undefined);
  }

  private enviarGravacao(aoSair: boolean) {
    if (!this.gravacao.length) return;
    const eventos = this.gravacao.splice(0, this.gravacao.length);
    this.mandar("/api/uso/gravacao", { sessao: this.aba, pagina: this.rota, eventos }, aoSair);
  }

  enviar(aoSair: boolean) {
    if (aoSair) this.fecharRolagem();
    if (this.fila.length) {
      const eventos = this.fila.splice(0, 200);
      this.mandar("/api/uso/eventos", { sessao: this.aba, eventos }, aoSair);
    }
    this.enviarGravacao(aoSair);
    if (aoSair) this.maiorRolagem = 0;
  }

  parar() {
    this.enviar(true);
    this.timers.forEach(clearInterval);
    this.pararGravacao?.();
    this.ligado = false;
  }
}

export const monitor = new Monitor();
