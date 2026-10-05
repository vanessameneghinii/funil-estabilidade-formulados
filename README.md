# Funil de estabilidade de produtos formulados

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-2.3-150458?logo=pandas&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.9-F7931E?logo=scikitlearn&logoColor=white)
![Pandera](https://img.shields.io/badge/Pandera-0.32-2E6B8A)
![matplotlib](https://img.shields.io/badge/matplotlib-3.11-11557C)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**Em uma frase:** no dataset sintético de 300 formulações, 42,3% sobrevivem aos 90 dias; entre as 199 que chegam ao Estágio 3, um modelo que usa só os ensaios do dia zero separa as que falham com AUC 0,82 (n = 44 lotes de teste, divisão temporal).

**In short:** synthetic stability study of 300 cleaning-product formulations in a three-stage funnel (bench screening, preliminary stability, accelerated stability). 127 formulations (42.3%) survive 90 days. Among the 199 that reach stage 3, a Random Forest using only day-0 assays separates those that fail with AUC 0.82 (44 test lots, temporal split). All data are synthetic.

Simulação de controle de qualidade e estudo de estabilidade de saneantes (produtos de limpeza) formulados, modelado como o funil de três estágios usado na prática de laboratório de desenvolvimento: triagem de bancada → estabilidade preliminar → estabilidade acelerada.

A pergunta que o projeto responde: **é possível prever, com os ensaios do dia zero, quais formulações sobrevivem aos 90 dias de estudo de estabilidade?**

> **Status:** completo: dataset, validação, funil, previsão antecipada, clusterização de assinaturas de degradação, e modelo semântico com relatório de três páginas em Power BI (pasta `powerbi/`).

📄 **Leitura rápida aqui no README** | 📊 **[Relatório técnico completo](relatorio/relatorio_tecnico.md)**: metodologia, justificativa de cada decisão de domínio e todos os números por trás de cada figura

## Por que isso importa

Cada formulação que entra no estudo acelerado ocupa câmara climática, bancada e analista por 90 dias. Antecipar a reprovação em meia hora de triagem pode economizar três meses de ciclo de desenvolvimento.

## Os três estágios

| Estágio | Ensaios avaliados | Quando | Critério de decisão |
|---|---|---|---|
| **1. Teste Inicial** | pH, densidade, ΔE₀₀ de liberação, aspecto, odor, estufa 50 °C, centrifugação, agitação magnética | dia 0 | se reprova em qualquer ensaio, encerra o estudo |
| **2. Estabilidade Preliminar** | pH, densidade, ΔE₀₀, aspecto, odor, sob choque térmico (geladeira 5 °C ↔ estufa 40 °C, dias alternados) | 15 e 30 dias | se reprova ao final de 30 dias, encerra o estudo |
| **3. Estabilidade Acelerada** | pH, densidade, ΔE₀₀, aspecto, odor, em 4 condições de armazenamento (ambiente escuro 25 °C, estufa 40 °C, geladeira 5 °C, luz solar) | 7, 15, 30, 60 e 90 dias | resultado final aos 90 dias |

Os parâmetros e o texto descritivo livre por ensaio foram elaborados para serem idênticos a uma planilha de controle de qualidade real, ver `data/README.md` para o dicionário de dados completo.

## Estrutura

```
data/      dados gerados (ver data/README.md para o dicionário de dados)
src/       pipeline numerado, 01 a 05 ("Passo N" neste README = script de número N); 06 exporta as tabelas do modelo Power BI
output/    figuras e métricas
relatorio/ relatório técnico com a justificativa das escolhas de domínio
powerbi/   modelo semântico em estrela, medidas DAX, scripts M, validação e relatório de 3 páginas (ver powerbi/README_MODELO.md)
```

## Como rodar

```bash
pip install -r requirements.txt
OUT_DIR=data python src/01_gerar_dataset.py        # gera os 7 CSV em data/
python src/02_preparar_dados.py                    # valida schema, julga vs. spec, diagnostica qualidade
python src/03_analise_funil.py                      # atrito, causas, efeito de fornecedor
python src/04_previsao_antecipada.py                 # previsão antecipada, 3 horizontes
python src/05_clusterizacao.py                       # agrupamento por assinatura de degradação
python src/06_exportar_modelo_bi.py                  # regera powerbi/dados_modelo e os valores de referência do Power BI
```

Todo o pipeline é determinístico (seed 42): rodar do zero reproduz `data/` e `output/` por inteiro, byte a byte nas colunas numéricas.

## Resultados principais

### Funil

Das 300 formulações que entram no Teste Inicial, 241 passam o Estágio 1, 199 chegam à Estabilidade Acelerada e 127 sobrevivem aos 90 dias: 42,3% cumulativo (sobre tudo que entrou) e 63,8% condicional (sobre quem chegou ao Estágio 3). São perguntas diferentes; a definição de cada uma está em `relatorio/relatorio_tecnico.md`.

![Funil, causas de reprovação e efeito do fornecedor](output/figures/02_funil_causas_fornecedor.png)

O fornecedor de tensoativo já separa levemente a aprovação no Teste Inicial (χ² = 7,14, p = 0,028, n = 300), e separa com muito mais força a sobrevivência aos 90 dias (χ² = 16,18, p < 0,001): FOR-B sobrevive a 32,2% contra 58,8% do FOR-C. O efeito existe desde o dia 0, mas fica bem mais forte com o tempo.

Os outros dois painéis da figura respondem duas perguntas complementares. O painel b mostra que cada estágio reprova majoritariamente por um ensaio diferente: o Estágio 1 reprova por ensaio de estresse físico (estufa, agitação, centrifugação), os Estágios 2 e 3 reprovam por deriva ao longo do tempo (aspecto, odor, pH). O painel d mostra, por família, a distância entre a taxa de sobrevivência cumulativa e a condicional: o Limpador Multiuso tem a maior distância (32,7% → 64,0%), ou seja, passa relativamente bem a triagem inicial, mas mais de um terço (36%) das formulações que chegam ao Estágio 3 não sobrevive aos 90 dias.

### Previsão antecipada

Entre as 199 formulações que chegam ao Estágio 3 (as outras 101 já foram reprovadas antes e não entram no modelo), um Random Forest treinado só com os ensaios do Teste Inicial (dia 0) prevê a sobrevivência aos 90 dias com AUC 0,821, contra 0,500 de baseline de classe majoritária (n = 44 lotes de teste, divisão temporal). É um ponto único, sem intervalo de confiança (ver Limitações). O recall na classe de falha é 55,6% (10 de 18 falhas capturadas), com limiar calibrado por custo (4:1 entre deixar passar uma falha e investigar uma formulação boa à toa).

![Previsão antecipada: ganho por horizonte, matriz de confusão, importância e divisão temporal](output/figures/03_previsao_antecipada.png)

Esperar 30 ou 37 dias não melhora a previsão: a AUC fica entre 0,77 e 0,82 nos três horizontes, sem tendência de subida, porque o sinal que decide o desfecho já está presente no dia 0. A validação aleatória, mantida como controle, dá AUC entre 0,82 e 0,89, igual ou mais alta que a temporal em todos os horizontes.

### Clusterização

Agrupando os 199 lotes que chegaram ao Estágio 3 pela assinatura de degradação (a inclinação de pH, amarelecimento e escurecimento em cada condição), o K-means encontra k = 2 (silhueta 0,39, confirmado por clusterização hierárquica Ward: ARI = 1,0 entre os dois métodos). O agrupamento não segue as 6 famílias declaradas (ARI = 0,26 contra a família nominal), mas também não divide nenhuma: cada família cai inteira em um cluster, e os clusters juntam famílias diferentes. Um cluster reúne Alvejante e Desinfetante, mais fotossensíveis (a inclinação média do amarelecimento sob luz solar é cerca de 30% maior) e com menor deriva térmica de cor (cerca de 20% menor na estufa); o outro reúne as quatro demais famílias.

![Clusterização por assinatura de degradação](output/figures/04_clusterizacao.png)

### Qualidade do dado (Passo 2)

Dos 300 lotes, a regra reconstruída a partir da `spec_master` reproduz a disposição registrada em 292 (as 8 divergências restantes vêm todas de medição fisicamente impossível). Dez lotes foram reprovados indevidamente por erro de laboratório simulado (oito por casa decimal deslocada, um por replicata trocada e um por desvio da sonda de pH). Separadamente, a sonda PH-02 foi simulada com offset de +0,35 de pH entre 1º de setembro e 15 de novembro de 2024: o teste mensal não sinalizou nenhum mês isolado, e a varredura em janelas de 3 meses recuperou o intervalo (setembro a novembro) com offset estimado de +0,26, abaixo do valor injetado. O kappa quadrático entre analistas ficou entre 0,84 e 0,92.

![Viés de instrumento: pH registrado por sonda ao longo do tempo, com a janela de deriva destacada](output/figures/01_vies_instrumento.png)

### Modelo e relatório em Power BI

O mesmo dataset foi modelado em estrela no Power BI para responder: **quanto do tempo de câmara climática é consumido por formulações que acabam reprovadas, e onde (família, fornecedor, causa) esse desperdício se concentra?** No dataset sintético, 37,2% dos dias-câmara (29.340 de 78.870) foram ocupados por lotes que não sobreviveram aos 90 dias.

- 10 tabelas (2 fatos, 1 ponte muitos-para-muitos e 7 dimensões, incluindo o calendário gerado em M), mais 3 tabelas auxiliares (medidas, seletor e parâmetro de custo); 43 medidas DAX e um relacionamento inativo para o papel duplo da data.
- As medidas foram validadas no Power BI Desktop contra valores calculados de forma independente em pandas (`powerbi/valores_de_referencia.csv`, `powerbi/referencia_mensal.csv` e `powerbi/referencia_inteligencia_tempo.csv`).
- O custo em reais é uma premissa ilustrativa (parâmetro what-if); o número principal é a fração de dias-câmara.

![Página 2 do relatório](powerbi/imagens/pagina2_camara_e_custo.png)

Detalhes, decisões de modelagem e o registro dos testes: [powerbi/README_MODELO.md](powerbi/README_MODELO.md).

## Decisões técnicas

Justificativa completa de cada item em [`relatorio/relatorio_tecnico.md`](relatorio/relatorio_tecnico.md).

- **ΔE₀₀ (CIEDE2000)** para diferença de cor: a fórmula que a ASTM D2244 recomenda para diferenças de 0 a 5 unidades, faixa em que este projeto opera (a alternativa mais antiga, ΔE\*ab de 1976, sub-representa a diferença perceptual nessa faixa).
- **ΔE de liberação (lote vs. padrão, no T0) é mantido separado do ΔE de fotoestabilidade** (lote vs. si mesmo, sob luz solar, aos 90 dias): são perguntas fisicamente diferentes. Tratá-las como uma métrica única geraria colinearidade perfeita entre elas e um critério de liberação fisicamente absurdo (reprovar um lote por exposição solar acumulada, não por desvio do padrão comercial).
- **Regra de liberação conjuntiva (AND):** todo parâmetro declarado precisa estar conforme; nenhum compensa outro fora de especificação. Score ponderado entra só como ferramenta de priorização, na importância por permutação do Passo 4.
- **A `spec_master` é a única fonte de verdade dos limites**: nenhum script reimplementa um limite em código; ela é versionada por vigência (a tolerância de cor mudou em 2024-10-01) e tem exceções documentadas por família (precipitado fino aceito em 2 famílias).
- **Validação de schema (Pandera) na ingestão**, separada da lógica de negócio: o schema falha por estrutura malformada (coluna ausente, categoria desconhecida); a Seção 5–10 do Passo 2 é que decide se um valor é fisicamente impossível ou apenas fora de especificação; confundir as duas transformaria o diagnóstico de qualidade do dado em erro do script.
- **Divisão temporal para validar o modelo**, com a divisão aleatória mantida só como controle explícito, o que corresponde ao uso real: prever formulações futuras com um modelo treinado no passado.
- **`analista` e `instrumento_ph`** foram intencionalmente excluídos do conjunto de features do Passo 4. A inclusão desses atributos introduziria o risco de o modelo aprender o viés instrumental originado no Passo 2 (associado à sonda PH-02 descalibrada) mascarado como sinal preditivo, o que comprometeria a captura da relação química real da formulação.
- **Ensaios de fase (centrifugação, agitação) são condicionados ao tipo físico da família** (emulsão, suspensão ou solução). Só emulsão e suspensão têm fase dispersa para separar; aplicar a mesma taxa de defeito de fase a uma solução descreveria um fenômeno que não existe naquele produto. A probabilidade de defeito e o vocabulário descritivo agora dependem do tipo físico real de cada uma das 6 famílias.

## Limitações

- **Dataset inteiramente sintético.** Não é dado industrial real, e nenhum valor aqui deve ser lido como especificação de produto (ver `FONTES.md` para o que é literatura [LIT] e o que é estimativa de engenharia [EST]).
- **n = 300 formulações**, das quais só 199 chegam ao Estágio 3: viés de seleção do próprio funil, que filtra antes de gerar dado de estabilidade completa. Reduz o n efetivo do modelo do Passo 4 para 199, e o teste temporal para 44.
- **Gap de otimismo entre divisão temporal e aleatória:** AUC 0,821 na temporal (a métrica que vale) contra 0,824 na aleatória em H0, mas a diferença cresce em H1 e H2 (0,80/0,77 temporal contra 0,89/0,88 aleatória). A causa mais provável é a revisão de spec de 2024-10-01, que desloca a distribuição do alvo entre treino e teste; não foi investigada formalmente.
- **Nenhum intervalo de confiança nas métricas do Passo 4**: são estimativas pontuais em n = 44 de teste. Um bootstrap ou repetição da divisão temporal com folds deslizantes daria a incerteza; não foi feito nesta versão.
- **Limiar de custo (4:1) é arbitrário**, escolhido para ilustrar o método; calibração contra custo real de câmara climática ou de investigação de bancada fica para uma versão futura.
- **Clusterização usa só 12 features de inclinação** (pH, amarelecimento, escurecimento × 4 condições); densidade e aspecto/odor não entraram no vetor; um vetor mais rico poderia revelar mais que 2 clusters. Os dois grupos também refletem coeficientes de fotossensibilidade e de deriva térmica atribuídos a cada família no gerador de dados (estimativas de engenharia, sem fonte documentada em `FONTES.md`): o resultado valida o método, que recupera uma estrutura conhecida, mas não confirma uma explicação química.
- **O relatório de Power BI usa o mesmo dado sintético:** o custo em reais depende de uma premissa que não vem do dataset, e o deslocamento do PH-02 e a vantagem do FOR-C foram embutidos no gerador.
- **O que não foi avaliado:** cartas de controle e OOT sistemático (Passo 2 já mede candidatos, mas sem carta formal), SHAP em vez de importância por permutação, modelo de shelf life por regressão linear mista, dados de matéria-prima e genealogia de lote, todos na lista de Próximos Passos abaixo.

## Próximos passos

- cartas de controle (Shewhart, EWMA, CUSUM) e detecção de fora de tendência (OOT)
- estimativa de prazo de validade por modelo linear misto, com teste de poolabilidade de lotes
- monitoramento multivariado (T² de Hotelling) para os parâmetros correlacionados
- dados de matéria-prima e genealogia de lote

## Referências metodológicas

O desenho do estudo segue metodologia pública: ANVISA, *Guia de Estabilidade de Produtos Cosméticos* (Série Qualidade em Foco, vol. 1); ISO/TR 18811:2018; ICH Q1A(R2), Q1B, Q1D e Q1E. Métodos de ensaio: ASTM E70 e ISO 4316 (pH); ASTM D2244, ASTM E308 e ISO/CIE 11664-4/-6 (cor); ISO 22716 (boas práticas de fabricação). Tratamento de resultados fora de especificação conforme o *FDA Guidance for Industry: Investigating Out-of-Specification Test Results*.

Os dados são **inteiramente sintéticos**, gerados a partir dessa metodologia pública. O projeto não contém dado industrial real.

## Licença

MIT. Ver [LICENSE](LICENSE).
