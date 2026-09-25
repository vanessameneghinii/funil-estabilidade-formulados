# Relatório técnico — funil de estabilidade de produtos formulados

Documento de apoio ao [`README.md`](../README.md). Aqui vai a metodologia, a justificativa de cada escolha de domínio e os números completos por trás de cada figura. Todos os dados são sintéticos (ver `../FONTES.md`); nenhum valor deriva de produto, cliente ou processo de uma empresa real.

---

## 1. Desenho do estudo

O funil tem três estágios, cada um com um portão de decisão — a estrutura que existe na prática de laboratório de desenvolvimento, não uma simplificação didática:

| Estágio | Ensaios | Avaliações | Efeito da reprovação |
|---|---|---|---|
| 1. Teste Inicial | pH, densidade, ΔE₀₀ de liberação, aspecto, odor, estufa 50 °C, centrifugação, agitação magnética | dia 0 | encerra a formulação |
| 2. Estabilidade Preliminar | pH, densidade, ΔE₀₀, aspecto, odor sob choque térmico (geladeira 5 °C ↔ estufa 40 °C, dias alternados) | 15 e 30 dias | encerra ao fim de 30 dias |
| 3. Estabilidade Acelerada | mesmos parâmetros em 4 condições de armazenamento | 7, 15, 30, 60 e 90 dias | desfecho final aos 90 dias |

A justificativa metodológica de cada tempo e condição está em `../FONTES.md`: o desenho segue a estrutura de estudo da ISO/TR 18811:2018 e do guia de estabilidade de cosméticos da ANVISA, e a fotoestabilidade segue a lógica de dose do ICH Q1B (a exposição à luz é medida em dose acumulada, não em tempo de relógio — daí a condição "Luz Solar" ter mecanismo de deriva próprio).

**Regra de liberação: conjuntiva (AND), nunca por score.** Todo parâmetro declarado tem que estar conforme; não existe compensação entre atributos. Isso é o que a `spec_master.csv` implementa: cada ensaio tem seu próprio limite e vigência, e a reprovação em qualquer um encerra o lote. Um score ponderado poderia até ser calculado a partir dos mesmos dados — e é, no Passo 4, como ferramenta de priorização (importância por permutação) — mas nunca decide liberação.

---

## 2. Geração do dataset (`01_gerar_dataset.py`)

### 2.1 Mecanismo de deriva

Cada lote recebe uma **qualidade latente** (robustez da emulsão), sorteada com viés por fornecedor de tensoativo. Essa variável governa **duas coisas simultaneamente**: os escores de estresse do Teste Inicial (estufa 50 °C, centrifugação) e as taxas de deriva na Estabilidade Acelerada. É esse acoplamento que torna a previsão antecipada possível sem vazamento — o dia 0 e o dia 90 são observações ruidosas da mesma variável oculta, não dados desconectados que o modelo aprenderia a colar por acaso.

A robustez latente **nunca é exposta como feature**: ela é descartada na gravação do CSV (`e1.drop(columns=["robustez_latente"])`). Isso é deliberado — se ela estivesse disponível, o modelo do Passo 4 a usaria diretamente e a previsão deixaria de ser sobre química mensurável.

A deriva tem dois mecanismos distintos, escolhidos para serem recuperáveis por análise (e recuperados: ver §5):
- **Térmico (Arrhenius):** atua em pH e densidade, proporcional à temperatura de armazenamento.
- **Fotoquímico (dose-dependente):** atua em b\* (amarelecimento) e L\* (escurecimento), só na condição "Luz Solar".

### 2.2 Cor: CIEDE2000, calculado, não sorteado

O dataset sorteia L\*, a\*, b\* da amostra em torno do padrão da família e **calcula** o ΔE₀₀ a partir dos três componentes — nunca sorteia o ΔE diretamente. Isso tem duas consequências corretas: o ΔE é não-negativo e assimétrico por construção (como um ΔE real), e os componentes dL\*/da\*/db\* ficam disponíveis para diagnóstico de causa (amarelecimento vs. escurecimento), que é exatamente o que a clusterização do Passo 5 usa.

**ΔE₀₀ (CIEDE2000), não ΔE\*ab (1976).** A ASTM D2244 recomenda ΔE₀₀ para diferenças de 0 a 5 unidades — a faixa em que a liberação e a maior parte da estabilidade deste projeto operam. Usar a fórmula de 1976 nessa faixa sub-representa a diferença perceptual real.

### 2.3 Duas tolerâncias de cor, deliberadamente diferentes

- `delta_e_liberacao` — lote vs. padrão da família, no T0. Tolerância apertada (spec: 1,50 a partir de 2024-10-01; 2,00 antes — ver §4).
- `delta_e_estabilidade` / `delta_e_estabilidade_luz` — lote vs. **si mesmo**, ao longo do estudo. Tolerância mais larga, e a condição de luz tem limite próprio (fotoestabilidade, ICH Q1B) porque alteração de cor sob exposição solar direta é um *endpoint* de estudo, não um critério de liberação.

Confundir essas duas tolerâncias — julgar liberação pelo ΔE de 90 dias sob luz — foi um erro real cometido na primeira versão deste dataset (documentado no histórico do projeto): o ΔE de liberação chegava a 11 unidades porque na verdade media estresse fotoquímico acumulado, não desvio de padrão. A correção está encapsulada na função `oos_estabilidade()`, com o limite de cor condicionado à condição de armazenamento.

### 2.4 Erros de laboratório injetados (gabarito)

42 erros distribuídos em 3 tipos, cada um com mecanismo realista:

| Tipo | n | Mecanismo | Detectável por outlier univariado? |
|---|---|---|---|
| Decimal deslocado | 8 | fator 10× no registro | Sim — recall 100% (faixa física e MAD) |
| Replicata trocada | 5 | duas leituras invertidas | Parcial — recall 60% |
| Sonda descalibrada | 24 | offset sistemático de instrumento, set–nov/2024 | **Não** — recall 4–13%, requer comparação entre instrumentos |

O terceiro tipo é o ponto pedagógico do dataset: um offset aditivo mantém cada valor individualmente plausível. Nenhuma comparação de um valor contra seus pares o encontra — só a comparação **entre instrumentos**, ao longo do tempo, revela o desvio (§3.4).

---

## 3. Preparação e qualidade do dado (`02_preparar_dados.py`)

### 3.1 Validação de schema (Pandera) — o que ela valida e o que não valida

A ingestão dos 7 CSV passa por schemas Pandera que verificam **estrutura**: coluna presente, tipo correto, categoria pertencente ao conjunto esperado. Eles **não** verificam a plausibilidade física do valor medido — um pH de 48,70 passa pelo schema (é um `float` válido) e só é sinalizado como impossível na Seção 5 do script, que é a lógica de negócio, não de ingestão.

A fronteira importa: se o schema rejeitasse valores fisicamente impossíveis, o script falharia exatamente no dado que ele foi escrito para diagnosticar. A distinção prática:

- **Schema (Pandera):** um LIMS que exportasse `"Aprovada"` em vez de `"Aprovado"`, ou omitisse uma coluna — falha de ingestão, corrige-se a origem do dado.
- **Regra de negócio (Seções 5–10):** um pH de 48,70 num CSV bem formado — falha de medição, gera diagnóstico (outlier, medição inválida) com contagem.

Na prática, o schema já pegou um bug real durante o desenvolvimento: a condição `"Choque Termico 5C/40C"` da Estabilidade Preliminar não estava na lista de valores aceitos (o schema tinha sido copiado do Estágio 3, que usa 4 condições diferentes). Falhou alto e claro antes de qualquer cálculo, com a coluna e o valor exatos.

### 3.2 Junção pela vigência da especificação, não pela spec atual

Cada medição é julgada contra a versão da `spec_master` vigente **na data da amostra**, via junção "as-of" (a data cai dentro da janela `vigente_de`–`vigente_ate`). A tolerância de cor na liberação foi revisada de 2,00 para 1,50 em 2024-10-01 (justificada pela implantação de um colorímetro de bancada mais preciso). Ignorar a vigência — julgar tudo pela spec de hoje — mudaria a disposição de **4 lotes**. É um número pequeno, mas o script existe para medir exatamente esse tipo de erro sistemático que uma auditoria descuidada cometeria.

### 3.3 Teste de sanidade: a regra reconstruída bate com o registro?

Reaplicando a `spec_master` desde o zero sobre as medições do Estágio 1, a disposição calculada coincide com `status_estagio1` em **293 dos 300 lotes**. As 7 divergências são **todas** explicadas por medição fisicamente impossível — nenhuma é erro de regra. Isso é o resultado que valida a Seção 2.4 do gerador e a Seção 6 do preparador ao mesmo tempo: a regra de negócio é reproduzível byte a byte a partir da especificação.

### 3.4 Viés de instrumento: dois testes, resoluções diferentes

O offset da sonda PH-02 é detectado comparando os dois instrumentos por período, sobre o **resíduo** em relação ao alvo de pH da família (o resíduo remove o efeito de família, maior que o offset procurado).

- **Teste mensal** (Mann-Whitney, correção de Bonferroni para 18 meses testados, limiar 0,0028): sinaliza só **setembro/2024**. Com ~8 lotes por instrumento por mês, falta potência para o offset real de +0,35.
- **Varredura em janela de 3 meses**: recupera o span **julho a novembro de 2024**, com offset estimado de **+0,305** — próximo do valor real, com um mês de sobra no início.

Os dois são reportados juntos porque respondem perguntas diferentes: o mensal tem mais especificidade (localiza com precisão de mês), o trimestral tem mais sensibilidade (localiza com precisão de trimestre, mas encontra o efeito). Reportar só um dos dois seria menos honesto que reportar os dois com essa ressalva.

### 3.5 Detecção de outlier nas séries de estabilidade: duas tentativas erradas, documentadas

O script tentou, nesta ordem:
1. **Filtro de Hampel direto na série** → 220 sinalizações espúrias. A série deriva por construção; o filtro marca as pontas da tendência, que são o comportamento esperado.
2. **Remover a tendência e filtrar o resíduo** → 451 sinalizações, pior ainda. Cada série tem 5 pontos; 2 graus de liberdade vão para a reta ajustada, e o MAD dos resíduos fica instável.
3. **Comparar cada lote com os outros lotes da mesma família/condição/tempo** (intervalo de tolerância por ponto — a lógica de detecção de fora de tendência, OOT) → **32 candidatos em 12.647 medições avaliadas (0,25%)**, em 14 lotes. Funciona porque a referência passa a ter dezenas de observações, não cinco.

As três tentativas ficam comentadas no próprio script, com os números de cada uma — é mais informativo para quem lê o código do que só a versão final.

### 3.6 Resultado agregado

| Métrica | Valor |
|---|---|
| Medições totais | 30.691 |
| Fora de especificação (OOS) | 360 (103 / 49 / 208 por estágio) |
| Fisicamente impossíveis | 8 |
| Reprovados indevidamente por erro de laboratório | 10 |
| Kappa quadrático (aspecto / centrifugação / estufa) | 0,876 / 0,928 / 0,910 |
| Taxa de discordância entre analistas | 17,3% (n = 225 reavaliações) |

---

## 4. Análise do funil (`03_analise_funil.py`)

### 4.1 Atrito, com as duas taxas separadas

| | n | % |
|---|---|---|
| Entram no Teste Inicial | 300 | — |
| Passam o Estágio 1 | 247 | 82,3% |
| Passam a Estabilidade Preliminar | 209 | 69,7% |
| Sobrevivem aos 90 dias | 128 | **42,7% cumulativo** / **61,2% condicional** |

Cumulativa = sobreviventes / todos que entraram (a taxa de negócio: "de cada 100 formulações que começo, quantas terminam?"). Condicional = sobreviventes / quem chegou ao Estágio 3 (a taxa que importa para o modelo do Passo 4, porque ele só vê quem chegou lá). Misturar as duas sem dizer qual é qual é o erro mais comum em análise de funil.

### 4.2 Cada estágio reprova por um ensaio diferente

Estágio 1 reprova majoritariamente por **ensaio de estresse** (centrifugação 29, estufa 50 °C 24, agitação 18); Estágio 2 e 3 reprovam por **deriva no tempo** (aspecto 34 e 87, odor 11 e 51, pH 2 e 40). Isso valida o desenho de três estágios: se todos reprovassem pela mesma causa, os estágios seriam redundantes.

### 4.3 O fornecedor de tensoativo: efeito tardio

| Fornecedor | n | Aprovação E1 | Sobrevivência 90d (cumulativa) |
|---|---|---|---|
| FOR-A | 100 | 86,0% | 44,0% |
| FOR-B | 94 | 76,6% | **29,8%** |
| FOR-C | 106 | 84,0% | **52,8%** |

Teste qui-quadrado: E1 não separa por fornecedor (χ² = 3,25, p = 0,20); sobrevivência aos 90 dias separa (χ² = 10,92, p < 0,01). Nota de honestidade: o gerador atribui viés de fornecedor à qualidade latente (§2.1), que não é exposta como feature — este teste mede o efeito **observado** nos dados disponíveis, não usa a variável oculta. A interpretação de mecanismo (o viés se manifesta em deriva, não em estresse instantâneo) vem do desenho do gerador, é uma leitura pós-hoc documentada, não uma descoberta estatística cega.

### 4.4 Por família: a distância entre cumulativa e condicional é o custo dos dois primeiros portões

| Família | Aprov. E1 | Sobrev. cumulativa | Sobrev. condicional | ΔE fotoestabilidade não conforme |
|---|---|---|---|---|
| Alvejante sem Cloro | 81,6% | 24,5% | 37,5% | 2 |
| Amaciante (esterquat) | 82,0% | 26,0% | 44,8% | 1 |
| Limpador Multiuso | 88,0% | 44,0% | 57,9% | 3 |
| Desinfetante Quaternário | 77,4% | 45,3% | 64,9% | 6 |
| Detergente Lava-Louças | 77,3% | 56,8% | 78,1% | 1 |
| Detergente para Roupas | 87,0% | 59,3% | 78,0% | 2 |

O Alvejante tem a maior distância entre as duas taxas (24,5% → 37,5%): passa relativamente bem a triagem mas degrada muito ao longo dos 90 dias — consistente com decomposição de agente oxidante ao longo do tempo, mais que com defeito de formulação detectável no dia 0.

---

## 5. Previsão antecipada (`04_previsao_antecipada.py`)

### 5.1 Pergunta e população

Alvo: `falha_90d` (1 = reprovado em algum ponto da Estabilidade Acelerada). Restrito aos **209 lotes que chegaram ao Estágio 3** — prever o desfecho de quem nunca entrou no estudo não é a pergunta, e o funil já decidiu isso no Passo 4. Taxa de falha na população: 38,8% (81 de 209).

### 5.2 Três horizontes, features nunca vazam do futuro

| Horizonte | Features | O que representa |
|---|---|---|
| H0 — dia 0 | `d0_*` (pH, densidade, ΔE liberação, escores de estresse) | decisão no Teste Inicial |
| H1 — ~30 dias | H0 + `e2_*` (deriva na Preliminar) | decisão após o 2º portão |
| H2 — ~37 dias | H1 + `d7_*` (1ª leitura da Acelerada, 4 condições) | decisão com uma semana de câmara |

`analista` e `instrumento_ph` foram **excluídos de propósito**: são identidade de quem mediu, não propriedade do produto. Incluí-los arriscaria o modelo aprender "PH-02 entre set–nov/2024 = risco" — o viés de instrumento do Passo 2 disfarçado de sinal preditivo, e não a química da formulação.

### 5.3 Divisão temporal vs. aleatória

Treino: 163 lotes (2024-01-11 a 2025-02-13). Teste temporal: 46 lotes (2025-02-20 a 2025-06-28). A divisão aleatória usa a mesma proporção (78/22), estratificada, embaralhada — existe só como controle para expor o gap de otimismo, nunca como número a reportar como desempenho real.

### 5.4 Resultados (Random Forest, 400 árvores, profundidade 6, balanceado)

| Horizonte | Divisão | AUC | PR-AUC | Recall falha | Precisão falha |
|---|---|---|---|---|---|
| H0 (dia 0) | **Temporal** | **0,777** | 0,678 | 75,0% | 54,5% |
| H0 (dia 0) | Aleatória | 0,861 | 0,844 | 77,8% | 63,6% |
| H1 (~30 d) | Temporal | 0,783 | 0,722 | 56,2% | 64,3% |
| H1 (~30 d) | Aleatória | 0,895 | 0,872 | 66,7% | 75,0% |
| H2 (~37 d) | Temporal | 0,777 | 0,723 | 62,5% | 55,6% |
| H2 (~37 d) | Aleatória | 0,792 | 0,718 | 55,6% | 71,4% |
| Baseline (classe majoritária) | ambas | 0,500 | — | 0% | — |

**Achado principal: a AUC temporal não sobe com o horizonte** (0,777 → 0,783 → 0,777, dentro do ruído). O sinal que decide o desfecho já está presente no dia 0 — consistente com o mecanismo do gerador (§2.1): a variável latente que governa o estresse do dia 0 é a mesma que governa a deriva aos 90 dias, então observar mais tempo não adiciona informação nova, só confirma o que já estava lá. Isso é uma leitura post-hoc a partir do desenho do gerador — em um dataset real, o achado seria "a triagem de bancada já captura o essencial", sem a explicação causal disponível.

**Gap de otimismo:** a divisão aleatória supera a temporal em todos os horizontes (mais claramente em H0 e H1: 0,861 e 0,895 vs. 0,777 e 0,783). É o padrão esperado quando a distribuição do alvo desloca entre o período de treino e o de teste — candidato mais provável aqui é a revisão de spec de 2024-10-01, que muda o critério de liberação de cor no meio do período coberto pelos dados.

### 5.5 Limiar por custo

O limiar de decisão não é 0,5: é escolhido varrendo candidatos no conjunto de treino para minimizar custo esperado, com razão 4:1 entre falso negativo (deixar passar uma formulação que vai falhar — ocupa 90 dias de câmara antes de ser descartada) e falso positivo (investigar uma formulação boa à toa — um dia de revisão extra). Para H0/temporal, o limiar resultante é 0,414; aplicado ao teste, dá matriz de confusão VN=20, FP=10, FN=4, VP=12 — recall de 75% na classe de falha. A razão de custo é arbitrária (não calibrada contra dado real de custo de câmara) e está isolada em uma constante no topo do script, para poder ser discutida e trocada.

### 5.6 O que o modelo do dia 0 realmente usa

Importância por permutação (RF, H0, divisão temporal, 30 repetições): `centrifugacao_score` domina (queda de AUC de 0,088), seguido por densidade (0,025), resíduo de pH vs. alvo da família (0,021) e a própria família do produto (0,019). Odor conforme e cor (score) têm importância nula ou negativa — não contribuem além do ruído, o que é esperado: o odor é binário e raramente reprova, e o score de cor visual satura antes do ΔE₀₀ instrumental (ver `data/README.md`).

---

## 6. Clusterização por assinatura de degradação (`05_clusterizacao.py`)

### 6.1 O vetor: forma da deriva, não nível

Para os 209 lotes que chegaram ao Estágio 3, cada um recebe um vetor de 12 números: a **inclinação** (regressão linear no tempo) de pH, amarelecimento (Δb\*) e escurecimento (−ΔL\*) em cada uma das 4 condições de armazenamento. Padronizado (z-score) antes de agrupar. Usar inclinação em vez de nível absoluto é a decisão central: dois lotes com pH inicial diferente mas mesma taxa de deriva devem cair no mesmo grupo.

### 6.2 k = 2, escolhido pela silhueta, confirmado por método independente

Silhueta média por k testado (K-means, 2 a 8): pico em **k = 2 (silhueta 0,396)**. Uma clusterização hierárquica (Ward) sobre o mesmo vetor, cortada em 2 grupos, concorda **completamente** com o K-means (ARI = 1,0 entre os dois métodos) — dois algoritmos com lógicas diferentes convergindo na mesma partição é evidência de que a estrutura é real, não artefato do método.

### 6.3 O agrupamento corta as famílias declaradas

ARI entre o cluster descoberto e a família nominal: **0,27** — moderado-baixo, ou seja, o agrupamento **não** reproduz as 6 famílias comerciais.

| Cluster | n | Composição |
|---|---|---|
| 0 | 140 | Amaciante, Detergente Lava-Louças, Detergente para Roupas, Limpador Multiuso |
| 1 | 69 | Alvejante sem Cloro, Desinfetante Quaternário |

O Cluster 1 reúne as duas famílias de química oxidante/biocida (alvejante e desinfetante quaternário) e tem assinatura **mais fotossensível, menos termossensível** (z-score do centroide: +1,1 em amarelecimento sob luz, negativo sob estufa/ambiente/geladeira). O Cluster 0 é o padrão oposto: mais deriva térmica, menos fotoquímica. Isso é quimicamente plausível — agentes oxidantes tendem a ser mais sensíveis a fotólise — e é o tipo de achado que justifica bracketing/matrixing (ICH Q1D) entre produtos de famílias comerciais diferentes que compartilham mecanismo de degradação.

### 6.4 Limitação honesta

O vetor usa só pH e cor; densidade e os escores organolépticos (aspecto, odor) não entraram. Um vetor mais completo poderia revelar subestrutura dentro dos 2 clusters atuais — não foi testado nesta versão.

---

## 7. Referências

### Normas e guias regulatórios
- ANVISA — *Guia de Estabilidade de Produtos Cosméticos*, Série Qualidade em Foco, vol. 1
- ANVISA — RDC 59/2010 (art. 3º, classificação de risco de saneantes), RDC 184/2001, RDC 989/2025
- ISO/TR 18811:2018 — *Cosmetics — Guidelines on the stability testing of cosmetic products*
- ICH Q1A(R2), Q1B (fotoestabilidade), Q1D (bracketing e matrixing), Q1E (avaliação de dados de estabilidade), Q6A, Q9
- ASTM E70 (pH, eletrodo de vidro); ISO 4316 (pH de tensoativos)
- ASTM D2244 (cálculo de tolerância e diferença de cor); ASTM E308; ISO/CIE 11664-4 e -6; ASTM D1729 (avaliação visual)
- ISO 22716 (boas práticas de fabricação de cosméticos)
- *FDA Guidance for Industry: Investigating Out-of-Specification (OOS) Test Results for Pharmaceutical Production*

### Métodos estatísticos
- Iglewicz, B.; Hoaglin, D. — *How to Detect and Handle Outliers*, ASQC, 1993 (z-score modificado / MAD)
- Rousseeuw, P. J.; Van Zomeren, B. C. — "Unmasking multivariate outliers and leverage points", *JASA*, 1990
- Montgomery, D. C. — *Introduction to Statistical Quality Control*, Wiley (cap. 5–6, 9, 11)
- Literatura de detecção de fora de tendência (OOT) em estabilidade farmacêutica — carta de controle de regressão, intervalo de tolerância por ponto de tempo (usada no Passo 2, §3.5)

Ressalva geral: as faixas de especificação usadas neste dataset (`FONTES.md`) são convenção de prática industrial ou estimativa de engenharia — nenhuma norma citada prescreve valor de tolerância para pH, densidade ou ΔE em saneantes. As normas padronizam método de medição e estrutura de estudo; a especificação é definida e justificada pelo fabricante.
