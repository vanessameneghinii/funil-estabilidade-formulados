# Fontes das faixas de especificação

Toda faixa usada no gerador está classificada como **[LIT]** (faixa encontrada em literatura técnica, patente de formulação, formulação-modelo de fornecedor ou regulação) ou **[EST]** (estimativa de engenharia, com a justificativa química explícita). A distinção é deliberada: em produto formulado a especificação é definida e justificada pelo fabricante — nenhuma norma prescreve o número —, então o que se pode documentar é a faixa em que a química do sistema é estável, e é isso que está abaixo.

## Restrição regulatória transversal (ANVISA)

A classificação de risco de saneantes depende diretamente do pH. Um produto é de **Risco 1** (notificação) quando, entre outros requisitos, o valor de pH na forma pura a 25 °C é **maior que 2 e menor que 11,5**, e o produto não apresenta corrosividade nem atividade antimicrobiana. Produtos com pH ≤ 2 ou ≥ 11,5, ou com ação antimicrobiana, são de **Risco 2** (registro). Base: RDC nº 59/2010, art. 3º (atualizada pela RDC nº 989/2025) e RDC nº 184/2001, §1º e §2º — a redação de 2001 refere o pH em solução a 1% p/p, a de 2010 o pH na forma pura.

Duas consequências no dataset, ambas registradas em `data/familias_produto.csv`:

- o limite superior de pH do **Limpador Multiuso Alcalino** é 11,0, e não 11,5 — a especificação mantém margem deliberada do corte regulatório, porque um lote que derive acima de 11,5 muda a classificação do produto, não apenas reprova;
- o **Desinfetante Quaternário** é classificado como **Risco 2** por ter atividade antimicrobiana, independentemente do seu pH.

## Faixas por família

| Família | pH (min–alvo–max) | Classificação | Base |
|---|---|---|---|
| Detergente Líquido Lava-Louças | 6,80 – 7,60 – 8,60 | **[LIT]** | Formulações de lava-louças líquido são preferencialmente formuladas em pH 6,8 a 9,0 (patentes de composição detergente, Procter & Gamble) |
| Detergente Líquido para Roupas | 8,50 – 9,60 – 10,50 | **[LIT]** | Produtos de lavanderia ficam tipicamente em pH 9 a 11; formulações de detergente líquido pesado são descritas entre pH 7 e 10, preferencialmente 8,5 a 9,0. Formulação-modelo de fornecedor (Stepan nº 908, detergente líquido pesado): pH 10,5, densidade relativa 1,02, viscosidade 100–150 cps a 25 °C |
| Limpador Multiuso Alcalino | 9,50 – 10,20 – 11,00 | **[LIT+EST]** | Teto definido pela margem ao corte de Risco 1 da ANVISA (pH < 11,5); alvo e piso estimados para um multiuso alcalino comercial |
| Desinfetante Quaternário Concentrado | 6,00 – 7,00 – 8,00 | **[EST]** | Quaternários de amônio são estáveis em ampla faixa de pH e formulados próximos da neutralidade para reduzir corrosividade em superfícies e embalagem. Risco 2 pela atividade antimicrobiana |
| Amaciante de Roupas (esterquat) | 2,50 – 3,20 – 4,00 | **[LIT]** | A estabilidade hidrolítica da ligação éster do esterquat exige pH baixo: a literatura de patente indica pH neat de 2,0 a 5,0, preferencialmente 2,5 a 4,5 e mais preferencialmente 2,5 a 4,0. Com amaciantes não-éster o pH pode ser maior, tipicamente 3,5 a 8,0 |
| Alvejante Líquido sem Cloro | 3,50 – 4,20 – 5,00 | **[EST]** | A decomposição do peróxido de hidrogênio é catalisada por base; alvejantes líquidos de oxigênio são estabilizados em meio ácido. Faixa estimada a partir desse mecanismo |

## Densidade

Todas as faixas de densidade são **[EST]**, com uma âncora de literatura: a formulação-modelo de detergente líquido pesado citada acima tem densidade relativa **1,02 g/mL**. As demais foram estimadas a partir do teor de sólidos esperado de cada sistema — água a 1,000 g/cm³ como base, elevada por tensoativo e sais dissolvidos (detergentes e alvejante acima de 1,02; alvejante o mais alto, 1,030–1,060, pelo estabilizante e peróxido) e reduzida em dispersões de esterquat com menor teor de sólidos (amaciante, 0,985–1,010).

A largura de ± 0,012 a ± 0,015 g/cm³ em torno do alvo corresponde a uma especificação apertada, coerente com o uso da densidade como controle de dosagem de água e de ar incorporado.

## Cor

O padrão de cor de cada família em CIE L\*a\*b\* é arbitrário — define apenas o tom nominal do produto (amarelo, verde, azul, rosa). O que não é arbitrário é a **tolerância**: ΔE₀₀ ≤ 1,50 na liberação, ancorado no fato de que ΔE ≈ 1 corresponde ao limiar de percepção visual em comparação lado a lado. O ΔE é calculado por **CIEDE2000**, e não por ΔE\*ab de 1976, porque a ASTM D2244 recomenda explicitamente a equação ΔE₀₀ para diferenças na faixa de 0 a 5 unidades — que é exatamente a faixa de uma tolerância de liberação.

O limite de estabilidade é mais folgado (ΔE₀₀ ≤ 3,00) e o de fotoestabilidade sob luz solar, mais ainda (ΔE₀₀ ≤ 6,00), porque respondem a perguntas diferentes: "o lote saiu com a cor certa?" contra "o produto aguenta a vitrine?".

## Constantes cinéticas de deriva

Todas **[EST]**, calibradas para produzir um funil com atrito plausível (cerca de 20% na triagem e 35% na acelerada). A estrutura é que tem base física:

- **Arrhenius** com energia de ativação de 80 kJ/mol, dentro da faixa típica de degradação em produtos formulados (60–100 kJ/mol). Isso gera fator de aceleração de ≈ 4,7 entre 25 °C e 40 °C e de ≈ 0,1 na geladeira a 5 °C, consistente com a heurística de que 90 dias a 40 °C aproximam 1 a 2 anos de prateleira.
- **Ordenação das taxas de deriva de pH por mecanismo químico**, não sorteada: amaciante e alvejante têm as maiores taxas (hidrólise do éster do esterquat e decomposição do peróxido são reações que consomem/liberam prótons), o multiuso alcalino vem em seguida (carbonatação pelo CO₂ atmosférico), e os detergentes têm as menores. É por isso que alvejante e amaciante são as famílias com menor sobrevivência aos 90 dias no dataset — e isso é consequência da química que foi modelada, não de um sorteio.
- **Componente fotoquímico dependente de dose**, atuando em b\* (amarelecimento) e L\* (desbotamento) e praticamente não atuando no pH, isolado do componente térmico. A distinção segue o ICH Q1B, em que a variável de estresse da fotoestabilidade é a dose de radiação e não o tempo.

## Protocolo de estabilidade

Estrutura de três estágios, condições e pontos de tempo seguem metodologia pública: ANVISA, *Guia de Estabilidade de Produtos Cosméticos* (Série Qualidade em Foco, vol. 1); ISO/TR 18811:2018, que recomenda condições de ensaio — incluindo pares de 24 h quente/frio para choque térmico e temperatura intermediária de 30 °C — mas explicitamente não impõe critérios de aceitação, deixando ao fabricante especificar e justificar o protocolo; e ICH Q1A(R2), Q1B (dose de fotoestabilidade), Q1D (bracketing e matrixing) e Q1E (avaliação de dados de estabilidade).

Métodos de ensaio: ASTM E70 e ISO 4316 (pH); ASTM D2244, ASTM E308, ISO/CIE 11664-4 e -6 (cor); ASTM D2196 e ISO 2555 (viscosidade, caso seja incluída em versão futura). Tratamento de resultado fora de especificação conforme o *FDA Guidance for Industry: Investigating Out-of-Specification Test Results for Pharmaceutical Production*.

## O que isto não é

Nenhum valor deste documento vem de dado industrial real, de formulação proprietária ou de especificação interna de qualquer empresa. As faixas [LIT] vêm de literatura pública (patentes de formulação, formulações-modelo divulgadas por fornecedores de tensoativos, regulação da ANVISA); as [EST] são estimativas derivadas do mecanismo químico declarado em cada linha. O dataset é sintético e serve para demonstrar método de análise, não para substituir especificação de produto.
