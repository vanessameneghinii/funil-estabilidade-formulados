# Roteiro de teste no Power BI Desktop

Objetivo: montar o modelo e provar que cada medida DAX devolve o valor calculado em pandas. Tempo estimado: 1h30 a 2h, sem contar os visuais.

**Regra do roteiro:** cada etapa termina em uma **checagem**. Se a checagem falhar, pare e corrija antes de seguir. Um erro de tipo na etapa 2 reaparece como um número errado na etapa 7, e fica muito mais difícil de localizar.

Nada aqui foi executado no Desktop por quem escreveu o roteiro. As checagens vêm de `valores_de_referencia.csv` e `referencia_mensal.csv`, calculados em pandas.

## Etapa 0. Preparação

1. Atualize o Power BI Desktop para a versão mais recente. A **Exibição de consulta DAX** (ícone na barra lateral esquerda, abaixo de Exibição de tabela) é necessária nas etapas 6 e 7. Se não aparecer, procure em Arquivo > Opções e configurações > Opções > Recursos de visualização.
2. Em Arquivo > Opções > **Arquivo atual** > Carregamento de dados, desmarque a detecção automática de relacionamentos. A coluna `lote` existe em várias tabelas e a detecção cria relacionamentos errados.
3. Se quiser a etapa 9 (grupo de cálculo), instale o Tabular Editor 2 (gratuito). Ela é opcional.
4. Confirme que rodou `python src/06_exportar_modelo_bi.py` e que a pasta `powerbi/dados_modelo/` tem 9 CSVs.

## Etapa 1. Parâmetro do caminho

1. Página inicial > **Transformar dados**.
2. Gerenciar parâmetros > Novo parâmetro. Nome `pCaminhoDados`, tipo Texto, valor atual = caminho completo da pasta `powerbi\dados_modelo` (sem barra no final).

**Checagem:** ao escrever `pCaminhoDados & "\dLote.csv"` no Editor Avançado, o caminho resultante abre o arquivo. Se não abrir, o erro é o caminho, não o M.

## Etapa 2. Carregar as tabelas (Power Query)

Para cada arquivo em `powerbi/M/`, exceto `dCalendario.pq` e `pCaminhoDados.pq`: Nova fonte > Consulta em branco > Editor Avançado > apagar o conteúdo > colar o arquivo. Renomeie a consulta para o nome do arquivo (por exemplo `fMedicoes`).

Carregue **por último** `dCalendario.pq`, porque ela lê as colunas de `fMedicoes`.

**Checagem (no Power Query):** em Exibir, ative *Qualidade da coluna* e marque "Criação de perfil de coluna com base em todo o conjunto de dados". As colunas `data_amostra`, `data_inicio_lote` e `valor` devem mostrar 0% de erro.

Depois de Fechar e aplicar, abra a **Exibição de tabela** e confira a contagem de linhas de cada tabela (aparece no rodapé):

| Tabela | Linhas |
|---|---|
| `dLote` | 300 |
| `dCondicao` | 6 |
| `dEnsaio` | 11 |
| `dAnalista` | 4 |
| `dInstrumento` | 3 |
| `dCausa` | 8 |
| `fMedicoes` | 29.421 |
| `fOcupacaoCamara` | 78.870 |
| `pLoteCausa` | 212 |
| `dCalendario` | 731 |

**Problemas comuns:** datas aparecendo como texto ou com erro indicam cultura errada. O M usa `"en-US"` na conversão; se alguém trocou, volte. Booleanos como texto indicam que a etapa `Tipos` foi removida.

## Etapa 3. Tabela de datas

1. Selecione `dCalendario` > Ferramentas de tabela > **Marcar como tabela de datas** > coluna `Data`.
2. Classificar por coluna: `Mes` por `MesNum`; `DiaSemana` por `DiaSemanaNum`.

**Checagem:** `dCalendario` vai de 01/01/2024 a 31/12/2025.

## Etapa 4. Relacionamentos

Exibição de modelo. Crie manualmente (arrastando a coluna da dimensão para a coluna do fato), todos **1 para muitos, direção única**:

| De (1) | Para (*) | Ativo |
|---|---|---|
| `dCalendario[Data]` | `fMedicoes[data_amostra]` | sim |
| `dCalendario[Data]` | `fMedicoes[data_inicio_lote]` | **não** (desmarque "Tornar este relacionamento ativo") |
| `dCalendario[Data]` | `fOcupacaoCamara[data]` | sim |
| `dLote[lote]` | `fMedicoes[lote]`, `fOcupacaoCamara[lote]`, `pLoteCausa[lote]` | sim |
| `dCondicao[condicao]` | `fMedicoes[condicao]`, `fOcupacaoCamara[condicao]` | sim |
| `dEnsaio[ensaio]` | `fMedicoes[ensaio]` | sim |
| `dAnalista[analista]` | `fMedicoes[analista]` | sim |
| `dInstrumento[instrumento_ph]` | `fMedicoes[instrumento_ph]` | sim |
| `dCausa[causa]` | `pLoteCausa[causa]` | sim |

**Checagem:** são 12 linhas no total, uma delas tracejada. Nenhuma com seta dupla. Compare com `diagrama_exibicao_modelo.png`.

## Etapa 5. Tabelas e colunas calculadas

Há uma dependência circular de propósito entre uma coluna e uma medida: a coluna `dLote[Medicoes OOS do lote]` usa a medida `[Medições OOS]`, e a medida `[Lotes com algum OOS]` (etapa 6) usa essa coluna. Por isso a **ordem abaixo importa**. Se você criar a coluna antes da medida, o Desktop responde que `[Medições OOS]` não existe.

Abra `DAX/tabelas_e_colunas_calculadas.dax` e siga esta ordem (Modelagem > Nova tabela / Nova medida / Nova coluna):

1. **Três tabelas:** `_Medidas`, `dSeletorTaxa`, `dParametroCusto`.
2. **Uma medida, só esta por enquanto**, na tabela `_Medidas` (Nova medida):
   ```
   Medições OOS = CALCULATE ( COUNTROWS ( fMedicoes ), fMedicoes[oos] = TRUE () )
   ```
3. **Três colunas em `dLote`:** `Medicoes OOS do lote`, `Situacao de OOS`, `AnoMesInicio`, nesta ordem.
4. A ordenação por coluna listada no fim do arquivo.

A etapa 6 recria `[Medições OOS]` com a mesma definição, sem problema.

**Checagem:** `dLote[Medicoes OOS do lote]` tem soma 355 (a mesma contagem de medições OOS, distribuída por lote) e `Situacao de OOS = "Com OOS"` em 179 lotes.

## Etapa 6. Medidas

1. Exibição de consulta DAX > nova aba > cole `DAX/medidas.dax` inteiro > **Executar** (ele só define, não devolve nada útil) > botão **Atualizar modelo com alterações**.
2. Se o botão não gravar todas, crie as medidas uma a uma em `_Medidas`.

**Checagem:** `_Medidas` passa a listar 43 medidas. Erros de sintaxe aparecem na própria aba com a linha do problema; me envie a mensagem exata se ocorrer.

## Etapa 7. Validação numérica (a etapa que importa)

Em outra aba da exibição de consulta DAX, cole `DAX/validacao.dax` e execute **um bloco `EVALUATE` por vez** (selecione o bloco e use "Executar").

**Bloco 1 (totais):**

| Medida | Esperado |
|---|---|
| Lotes iniciados | 300 |
| Aprovados no Estágio 1 | 241 |
| Chegaram ao Estágio 3 | 199 |
| Sobreviventes 90d | 127 |
| Taxa cumulativa / condicional | 42,3% / 63,8% |
| Medições realizadas / julgáveis | 29.421 / 24.651 |
| Medições OOS / % OOS | 355 / 1,4% |
| Medições inválidas | 8 |
| Lotes com algum OOS | 179 |
| Dias-câmara / desperdiçados / % | 78.870 / 29.340 / 37,2% |
| Custo com premissa de R$ 50 | R$ 1.467.000 |
| Pico de ocupação | 199 |
| Desvio médio do pH vs alvo | -0,0892 |

**Bloco 2 (fornecedor):** FOR-A 116 lotes, 36,2%; FOR-B 87 lotes, 32,2%; FOR-C 97 lotes, 58,8%. O ranking deve ser FOR-C 1, FOR-A 2, FOR-B 3.

**Bloco 3 (família):** compare com as linhas `familia=` de `valores_de_referencia.csv` (taxas e pH por família; os valores de pH esperados estão em comentário no fim do bloco).

**Bloco 4 (instrumento):** PH-01 0,0175; PH-02 0,0869; N/D -0,0985.

**Bloco 5 (mensal):** compare linha a linha com `referencia_mensal.csv`. Dois meses para olhar primeiro:

| Mês | Lotes iniciados | Medições | Dias-câmara | Ocupação último dia | Pico |
|---|---|---|---|---|---|
| 2024-09 | 29 | 1697 | 4617 | 161 | 161 |
| 2025-05 | 14 | 2002 | 5804 | 175 | 199 |

**Bloco 6 (causas):** a soma de "Lotes" passa de 173 de propósito (212 causas registradas em 173 lotes reprovados).

### Se um número divergir

| Sintoma | Causa provável |
|---|---|
| Lotes iniciados = 0 ou em branco | O relacionamento inativo `data_inicio_lote` não foi criado, ou foi deixado ativo e o outro desativado |
| Taxas certas no total, erradas por fornecedor | `dLote` não filtra `fMedicoes` (direção do relacionamento ou chave trocada) |
| Dias-câmara certo, desperdício 0 | `dLote[sobreviveu_90d]` foi carregado como texto em vez de lógico |
| Medições certas, OOS 0 | `oos` ou `julgavel` carregados como texto |
| Pico ou ocupação por mês divergem, totais certos | `dCalendario` não cobre o intervalo, ou não foi marcada como tabela de datas |
| Causas com soma igual a 173 | Alguém criou filtro bidirecional na ponte |

## Etapa 8. Teste de comportamento (2 minutos cada)

Crie uma página de rascunho e confira o comportamento, não só os números:

1. **Papel duplo da data.** Uma tabela com `dCalendario[AnoMes]`, `[Lotes iniciados]` e `[Medições realizadas]`: as duas colunas não podem ser iguais (uma segue a data de início, a outra a data da amostra).
2. **Seletor de taxa.** Segmentador em `dSeletorTaxa[Definicao]` + cartão `[Taxa de sobrevivência (seletor)]`: alterna entre 42,3% e 63,8%.
3. **Ponte.** Matriz com `dCausa[causa]` e `[Lotes por causa]`; a linha de total deve mostrar 173, não a soma das linhas.
4. **Semiaditiva.** Mesma matriz por mês com `[Dias-câmara]` e `[Câmaras ocupadas (último dia com dado)]`: o total geral da segunda não é a soma dos meses.
5. **Semáforo.** Cor da fonte por *Valor do campo* em `[Cor do semáforo (% OOS)]` numa matriz por família.
6. **Parâmetro de custo.** Segmentador em `dParametroCusto` com seleção única: o custo muda proporcionalmente.

## Etapa 9. Grupo de cálculo (opcional)

Siga `DAX/grupo_de_calculo_visao_temporal.md`. Teste com `[Medições realizadas]` por mês: os itens "Atual", "Ano anterior" e "Variação" devem aparecer.

## Etapa 10. Salvar e registrar

1. Salve como `powerbi/funil-estabilidade.pbix`.
2. Tire capturas da Exibição de modelo e da página de validação.
3. Se quiser versionar as medidas exportadas do próprio modelo, use a exibição de consulta DAX: Exportar as medidas para um `.dax`.
4. **Me envie:** a mensagem de erro exata de qualquer etapa que falhar, e os números que divergirem (valor obtido × esperado). Com isso localizo o ponto do modelo ou do script.
