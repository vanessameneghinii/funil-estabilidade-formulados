# Grupo de cálculo: Visão temporal

Grupos de cálculo não são criados pela interface padrão do Power BI Desktop: usam o **Tabular Editor** (a versão 2 é gratuita) ligado ao modelo aberto (Ferramentas externas > Tabular Editor).

## Pré-requisito

Em Arquivo > Opções > Recursos de visualização / Configurações do modelo, ative **Descartar medidas implícitas**. O Tabular Editor faz isso ao criar o primeiro grupo de cálculo; sem isso o Power BI recusa o grupo.

## Objeto

- Tabela do grupo: `Visao temporal`
- Coluna do grupo: `Visao`
- Precedência: 10

## Itens (cada um é uma expressão DAX)

| Item | Ordinal | Expressão |
|---|---|---|
| Atual | 0 | `SELECTEDMEASURE ()` |
| Acumulado no ano | 1 | `CALCULATE ( SELECTEDMEASURE (), DATESYTD ( dCalendario[Data] ) )` |
| Ano anterior | 2 | `CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( dCalendario[Data] ) )` |
| Variação % vs ano anterior | 3 | ver abaixo |

Expressão do item **Variação % vs ano anterior**:

```dax
VAR atual = SELECTEDMEASURE ()
VAR anterior =
    CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( dCalendario[Data] ) )
RETURN
    IF ( NOT ISBLANK ( anterior ), DIVIDE ( atual - anterior, anterior ) )
```

Expressão de string de formato dinâmico (Format String Expression) desse mesmo item, para que o resultado apareça como percentual mesmo quando a medida-base é inteira:

```dax
"0.0%"
```

## O que o grupo evita

Sem ele, cada medida do modelo que precise de versão "acumulada", "ano anterior" e "variação" exigiria três medidas extras. Com as 43 medidas do modelo, seriam 129 medidas para manter (43 mais 3 versões de cada). O grupo aplica a mesma lógica temporal a qualquer medida colocada no visual: `[Lotes iniciados]`, `[Medições realizadas]`, `[Dias-câmara]`, `[Medições OOS]`.

## Cuidados

- Não aplique o grupo a taxas (`[Taxa cumulativa 90d]`) com o item "Acumulado no ano": a média acumulada de uma razão não é a razão dos acumulados. Para taxas, use apenas "Atual", "Ano anterior" e "Variação".
- As medidas de funil usam `USERELATIONSHIP` internamente. O grupo envolve a medida por fora com um filtro em `dCalendario[Data]`, e o filtro se propaga pelo relacionamento que a medida ativa. O comportamento é o esperado, mas confira com a série mensal de `referencia_mensal.csv`.
- Um item de grupo de cálculo que usa `SELECTEDMEASURE()` com medidas de formatos diferentes só converte o formato no item que define a expressão de formato dinâmico.
