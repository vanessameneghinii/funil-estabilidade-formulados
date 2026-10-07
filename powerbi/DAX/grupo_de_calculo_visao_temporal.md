# Grupo de cálculo: Visão temporal

Este grupo aplica a mesma lógica de tempo (atual, acumulado no ano, ano anterior e variação) a qualquer medida colocada no visual. Foi testado no Power BI Desktop (versão 2.158) numa cópia do modelo, pelo botão **Grupo de cálculo** da faixa Página Inicial, na Exibição de modelo; o `.pbix` publicado não inclui o grupo. O Tabular Editor também serve, mas não é necessário.

## Criação

1. Página Inicial > **Grupo de cálculo**. O Desktop avisa que vai **descartar medidas implícitas**: um modelo com grupo de cálculo só aceita medidas explícitas. Confirme.
2. Renomeie a tabela para `Visao temporal` e a coluna para `Visao`.
3. Crie os quatro itens abaixo (botão **+** ou clique direito na tabela > novo item de cálculo). Em cada item, a expressão vai na barra de fórmulas.

| Item | Expressão |
|---|---|
| Atual | `SELECTEDMEASURE ()` |
| Acumulado no ano | `CALCULATE ( SELECTEDMEASURE (), DATESYTD ( dCalendario[Data] ) )` |
| Ano anterior | `CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( dCalendario[Data] ) )` |
| Variação % vs ano anterior | ver abaixo |

Expressão do item **Variação % vs ano anterior**:

```dax
VAR atual = SELECTEDMEASURE ()
VAR anterior =
    CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( dCalendario[Data] ) )
RETURN
    IF ( NOT ISBLANK ( anterior ) && NOT ISBLANK ( atual ), DIVIDE ( atual - anterior, anterior ) )
```

A verificação dos dois valores evita uma variação de -100% nos meses sem dado (novembro e dezembro de 2025).

4. No item de variação, ative a **cadeia de caracteres de formato dinâmico** (painel Propriedades > Formatação) e escreva `"0.0%"`, com as aspas. Sem isso, a variação apareceria no formato da medida-base (0,0973 em vez de 9,7%). O campo de formato só aceita uma expressão que devolva o texto do formato; colar ali o DAX do item gera erro de definição inválida.

## Ordem dos itens

A ordem das colunas na matriz segue a posição dos itens na lista de itens de cálculo (aba Modelo do painel Dados), e pode ser ajustada arrastando os itens. O painel de propriedades do Desktop não expõe a propriedade `Ordinal`; ela pode ser editada no Tabular Editor.

## Teste

Matriz com `dCalendario[AnoMes]` em Linhas, `Visao temporal[Visao]` em Colunas e `[Dias-câmara]` em Valores:

| Mês | Atual | Acumulado no ano | Ano anterior | Variação |
|---|---|---|---|---|
| 2025-01 | 4.633 | 4.633 | 77 | 5.916,9% |
| 2025-06 | 5.040 | 28.411 | 3.944 | 27,8% |
| 2025-10 | 316 | 35.181 | 5.335 | -94,1% |
| 2025-11 | em branco | 35.181 | 5.596 | em branco |

Com `[Medições realizadas]`, em 2025-06: atual 1.523, acumulado 10.300, ano anterior 1.388 e variação 9,7% (valores de `referencia_inteligencia_tempo.csv`).

## O que o grupo evita

Sem ele, cada medida do modelo que precisasse de versão acumulada, de ano anterior e de variação exigiria três medidas extras. Com as 43 medidas do modelo, seriam 129 medidas adicionais, 172 no total. O grupo aplica a mesma lógica a qualquer medida colocada no visual.

## Cuidados

- Não aplique o item "Acumulado no ano" a taxas (`[Taxa cumulativa 90d]`): o acumulado de uma razão não é a razão dos acumulados. Para taxas, use apenas "Atual", "Ano anterior" e "Variação".
- Não aplique o grupo a medidas que já têm inteligência de tempo (por exemplo, `[Medições acumuladas no ano]`): o filtro de tempo seria aplicado duas vezes.
- Na linha de **Total**, o grupo avalia a expressão sobre o contexto do total, e não soma as linhas. No total de uma série de dois anos, "Ano anterior" é o ano de 2024 inteiro e a variação compara dois anos com um, o que não tem leitura analítica. Oculte o total ou limite a análise a um ano.
- A variação de janeiro de 2025 (5.916,9% em dias-câmara) compara com janeiro de 2024, quando a série mal tinha começado.
- O comportamento do grupo com as medidas de funil, que usam `USERELATIONSHIP` internamente, não foi testado.
