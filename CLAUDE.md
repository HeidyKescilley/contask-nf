# Contask NF
- Visão geral, regras do ADN, status por evento e comandos: README.md.
- NSU é exclusivo: a próxima chamada usa o maior NSU recebido, nunca +1.
- Sempre enviar `cnpjConsulta` ao ADN, inclusive para a própria empresa (sem ele o ADN devolve 400).
- Status da nota vem só de eventos, recalculado por chave. Nunca use cStat nem busca por texto.
- DANFSe é gerado localmente a partir do XML (NT 008/2026); a API /danfse do ADN foi suspensa.
- Nunca grave senha ou chave privada em texto puro, log ou resposta de API.
- Nunca faça commit de dados/, backups/, *.pfx, .env ou XMLs de clientes.
- Em produção, somente chamadas de leitura ao ADN. Não emitir, cancelar ou manifestar notas.
- Interface em pt-BR; datas dd/mm/aaaa; valores em R$.
- Toda tela deve funcionar nos dois temas e ter estados de carregamento, vazio e erro.
- Vários escritórios no mesmo SQLite; o escritório vem da sessão. Toda rota /api nova exige login automaticamente (middleware em core/seguranca.py); rota pública precisa entrar em ROTAS_PUBLICAS de propósito.
- A chave-mestra é CONTASK_CHAVE_MESTRA. Sem ela a API não sobe. Testes com dados reais: use uma instância isolada (CONTASK_DADOS_DIR próprio), nunca o banco real.

## Comandos
- Backend: `.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8765`
- Testes: `.venv\Scripts\python -m pytest`
- Migração do banco: `cd backend && ..\.venv\Scripts\alembic upgrade head`
- Frontend (dev): `cd frontend && npm run dev` (proxy para o backend); build: `npm run build`
- Aplicação completa: `iniciar.bat`; backup: `backup.bat`
