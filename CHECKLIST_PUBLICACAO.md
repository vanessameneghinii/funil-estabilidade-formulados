# Checklist de publicação — conferido em `funil-estabilidade-formulados`

Este arquivo é de trabalho — **não faz parte do repositório publicado** (adicione ao `.gitignore` local se quiser, ou simplesmente não dê `git add` nele).

## ✅ Já verificado automaticamente

- [x] `.gitignore` presente e cobre `__pycache__/`, `.venv/`, `.ipynb_checkpoints/`, `.vscode/`, `.idea/`
- [x] Nenhum `__pycache__` de fato presente na árvore (nada para limpar)
- [x] `requirements.txt` presente, com versões fixadas (pandas, numpy, scikit-learn, matplotlib, scipy, pandera)
- [x] `data/README.md` (dicionário de dados) presente
- [x] `FONTES.md` presente, com toda faixa marcada [LIT]/[EST] e a ressalva de que nenhum valor é dado real
- [x] Os 5 scripts (`01` a `05`) rodam do zero e reproduzem `data/` e `output/` (seed 42 fixo em todos)
- [x] As 5 figuras de `output/figures/` existem e foram verificadas geometricamente (sem texto sobreposto) e visualmente
- [x] Nenhum arquivo do repositório contém código de produto, código de lote, valor medido real ou menção a nano/microencapsulado — domínio é saneantes, 100% sintético

## ⬜ Sua ação antes de publicar

- [ ] **Trocar `SEU NOME AQUI` no `LICENSE`** pelo seu nome — é o único placeholder que sobrou
- [ ] Ler o Passo 1 do roteiro original mais uma vez: as faixas de spec fazem sentido pra você? (você já validou a estrutura; isso é a última conferência de conteúdo)
- [ ] Decidir o nome do repositório no GitHub (sugestão: `funil-estabilidade-formulados`, mesmo nome da pasta local)
- [ ] Apagar (ou não versionar) este arquivo e `CONFERIR_passo1_v2.xlsx` — são material de trabalho, não do repositório publicado
- [ ] Conferir se `output/figures/00_validacao_dataset.png` (referenciada no README) ainda existe na pasta — foi copiada do artefato original do Passo 1, confirme que está em `output/figures/`, não só na raiz

## ⬜ Opcional, mas de baixo custo e alto retorno

- [ ] Adicionar 1 frase no topo do `README.md` do tipo "portfólio pessoal, dataset sintético, ver seção Limitações" — antecipa a primeira pergunta de quem abre o repositório
- [ ] No GitHub, adicionar a descrição curta do repositório (o campo "About") com uma frase: a pergunta de negócio do projeto
- [ ] Se for anexar a um currículo/candidatura: o link direto para a seção "Resultados principais" do README (ancoragem `#resultados-principais`) economiza o tempo do avaliador

## Não fazer

- Não adicionar dashboard, API ou deploy — não estava no escopo da v1 e não é isso que está sendo avaliado num portfólio de analista/cientista de dados júnior
- Não "arrumar" o `data/README.md` para remover acentuação — se aparecer errado no terminal do Windows é o leitor, os arquivos estão em UTF-8 válido
- Não publicar `revisao_qualitiva_ml.md`, `guia_didatico_qualitiva_ml.md` nem `redesenho_projeto_dominio_real.md` (documentos de processo desta conversa) — eles não pertencem a este repositório
