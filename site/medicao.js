/* Medição do site Contask NF.
 *
 * 1. Visitas próprias (sempre): página, canal (utm_source ou site de origem) e tipo de aparelho vão para
 *    /api/publico/visita. Sem cookie, sem IP guardado, sem dado pessoal: não precisa de consentimento.
 * 2. Google Analytics 4 (só com consentimento, LGPD): o aviso aparece na primeira visita e o GA só carrega
 *    depois de "Aceitar". Preencha GA_ID com o ID da métrica (G-XXXXXXXXXX) para ligar.
 * 3. Eventos: window.contaskEvento(nome, dados) manda para o GA quando ele está ativo. Os formulários
 *    chamam "generate_lead"; cliques em WhatsApp e nos botões principais são contados aqui.
 */
(() => {
  const GA_ID = "";
  const CHAVE = "contask_cookies"; // "aceito" | "recusado"

  // --- 1. visitas próprias ---
  try {
    fetch("/api/publico/visita", {
      method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pagina: (location.pathname + location.search).slice(0, 300),
        referencia: document.referrer ? document.referrer.slice(0, 500) : null, largura: window.innerWidth }),
    }).catch(() => {});
  } catch (_) { /* sem rede: a página segue normal */ }

  // --- 2. Google Analytics com consentimento ---
  const ler = () => { try { return localStorage.getItem(CHAVE); } catch (_) { return null; } };
  const gravar = (v) => { try { localStorage.setItem(CHAVE, v); } catch (_) { /* navegação privada */ } };
  let gaAtivo = false;

  function carregarGA() {
    if (!GA_ID || gaAtivo) return;
    gaAtivo = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("consent", "default", { analytics_storage: "granted", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });
    window.gtag("js", new Date());
    window.gtag("config", GA_ID, { anonymize_ip: true });
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(GA_ID);
    document.head.appendChild(s);
  }

  window.contaskEvento = (nome, dados) => { if (gaAtivo && window.gtag) window.gtag("event", nome, dados || {}); };

  function aviso() {
    const caixa = document.createElement("div");
    caixa.className = "contask-cookies";
    caixa.setAttribute("role", "region");
    caixa.setAttribute("aria-label", "Aviso de cookies");
    caixa.innerHTML = '<p>Usamos cookies do Google Analytics para entender como o site é usado e melhorar as páginas. '
      + 'Nada é usado para anúncios.</p><div><button type="button" data-v="recusado">Recusar</button>'
      + '<button type="button" data-v="aceito" class="sim">Aceitar</button></div>';
    const css = document.createElement("style");
    css.textContent = ".contask-cookies{position:fixed;z-index:90;left:16px;right:16px;bottom:16px;max-width:560px;margin:0 auto;"
      + "display:flex;flex-wrap:wrap;gap:12px 16px;align-items:center;justify-content:space-between;padding:14px 16px;"
      + "background:#15181d;color:#eef0f3;border:1px solid #2c313a;border-radius:12px;box-shadow:0 18px 50px -20px rgb(0 0 0/.6);"
      + "font:13px/1.5 Geist,ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif}"
      + ".contask-cookies p{margin:0;flex:1 1 260px}.contask-cookies div{display:flex;gap:8px;margin-left:auto}"
      + ".contask-cookies button{font:600 13px/1 inherit;font-family:inherit;padding:9px 14px;border-radius:8px;cursor:pointer;"
      + "border:1px solid #3a404b;background:transparent;color:inherit}.contask-cookies button.sim{background:#fff;color:#0b0c0e;border-color:#fff}"
      + ".contask-cookies button:focus-visible{outline:2px solid #7d9bff;outline-offset:2px}";
    document.head.appendChild(css);
    caixa.addEventListener("click", (e) => {
      const v = e.target.closest("button") && e.target.closest("button").dataset.v;
      if (!v) return;
      gravar(v);
      caixa.remove();
      if (v === "aceito") carregarGA();
    });
    document.body.appendChild(caixa);
  }

  if (GA_ID) {
    const escolha = ler();
    if (escolha === "aceito") carregarGA();
    else if (escolha !== "recusado") aviso();
  }

  // --- 3. cliques que importam ---
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a");
    if (!a) return;
    const href = a.getAttribute("href") || "";
    if (href.includes("wa.me/")) window.contaskEvento("contato_whatsapp", { local: location.pathname });
    else if (/#(teste|oferta)$/.test(href) || href.includes("30-dias-gratis")) {
      window.contaskEvento("clique_cta", { texto: (a.textContent || "").trim().slice(0, 60), local: location.pathname });
    }
  });
})();
