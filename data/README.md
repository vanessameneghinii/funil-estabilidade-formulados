# Dicionário de dados

Todos os arquivos desta pasta são gerados por `src/01_gerar_dataset.py` (seed 42). Nenhum é editado à mão. A procedência de cada faixa de especificação está em [../FONTES.md](../FONTES.md).

| Arquivo | Coluna | Tipo | Descrição |
|---|---|---|---|
| `estagio1_teste_inicial.csv` | `data_inicio_teste` | data | Data do ensaio; usar para divisão temporal treino/teste |
| `estagio1_teste_inicial.csv` | `lote` | texto | Identificador SIGLA-AAMM-NNN |
| `estagio1_teste_inicial.csv` | `produto_familia / produto_sigla` | categórico | Uma das 6 famílias de saneante |
| `estagio1_teste_inicial.csv` | `fornecedor_tensoativo` | categórico | FOR-A/B/C; FOR-B tem viés negativo de qualidade |
| `estagio1_teste_inicial.csv` | `aspecto_desc / aspecto_score` | texto / ordinal 0-4 | Texto livre do analista e escore derivado (0=homogêneo, 4=separação franca) |
| `estagio1_teste_inicial.csv` | `cor_L / cor_a / cor_b` | numérico | CIE L*a*b* da amostra (D65/10°) |
| `estagio1_teste_inicial.csv` | `delta_L / delta_a / delta_b` | numérico | Desvio vs padrão da família; direção do desvio de cor |
| `estagio1_teste_inicial.csv` | `delta_e_liberacao` | numérico ≥0 | ΔE00 (CIEDE2000) lote vs padrão em T0; limite 1,50 |
| `estagio1_teste_inicial.csv` | `cor_score` | ordinal 0-4 | Avaliação VISUAL de cor; discorda do ΔE nas faixas limítrofes de propósito |
| `estagio1_teste_inicial.csv` | `odor_conforme / odor_desc` | booleano / texto | Indicador de rancidez |
| `estagio1_teste_inicial.csv` | `ph` | numérico | Faixa por família; valor absoluto (escala logarítmica) |
| `estagio1_teste_inicial.csv` | `densidade_g_cm3` | numérico | g/cm³, 3 decimais |
| `estagio1_teste_inicial.csv` | `estufa50_* / centrifugacao_* / agitacao_*` | texto / ordinal 0-4 | Ensaios de estresse da triagem; '-' quando não aplicável à família |
| `estagio1_teste_inicial.csv` | `analista / instrumento_ph` | categórico | ANL-01..03; PH-01/PH-02 (PH-02 tem offset em uma janela de datas) |
| `estagio1_teste_inicial.csv` | `status_estagio1 / causa_reprovacao_estagio1` | categórico / texto | Portão do estágio 1 (regra AND sobre spec_master) |
| `estagio1_teste_inicial.csv` | `observacoes` | texto | Registro de aceite por exceção de família |
| `estagio2_* / estagio3_*.csv` | `condicao / tempo_dias` | categórico / inteiro | E2: choque térmico, 15 e 30 d. E3: 4 condições, 7/15/30/60/90 d |
| `estagio2_* / estagio3_*.csv` | `delta_e_estabilidade` | numérico ≥0 | ΔE00 vs T0 do PRÓPRIO lote (não vs padrão) |
| `estagio2_* / estagio3_*.csv` | `oos_flag / causa_oos` | booleano / texto | Conformidade da avaliação; sob luz solar aplica-se o limite de fotoestabilidade |
| `funil_lotes.csv` | `status_estagio1/2/3_90d` | categórico | Desfecho em cada portão; NaN = não chegou ao estágio |
| `funil_lotes.csv` | `fotoestabilidade_90d` | categórico | Endpoint de luz, separado da decisão de estabilidade |
| `funil_lotes.csv` | `estagio_final / sobreviveu_90d` | categórico / booleano | ALVO do modelo de previsão antecipada |
| `spec_master.csv` | `limite_min / limite_max / criterio_tipo` | numérico / texto | Especificação por família e ensaio |
| `spec_master.csv` | `excecao_permitida` | texto | Regra de aceitação específica da família (ex.: precipitado fino normal) |
| `spec_master.csv` | `vigente_de / vigente_ate / versao_spec` | data / texto | Vigência: julgar cada resultado contra a spec da data da amostra |
| `avaliacao_duplicada_analistas.csv` | `escore_analista_1 / _2` | ordinal 0-4 | 25% dos lotes reavaliados; base para kappa de Cohen |
| `gabarito_erros_injetados.csv` | `tipo_erro / valor_registrado / valor_verdadeiro` | texto / numérico | GABARITO: não usar como feature; serve para medir recall do detector de outlier |
| `familias_produto.csv` | `sigla / produto_familia` | texto | Identificação da família (6 famílias de saneante) |
| `familias_produto.csv` | `classificacao_anvisa` | categórico | Risco 1 (notificação) ou Risco 2 (registro); ver FONTES.md |
| `familias_produto.csv` | `ph_min / ph_alvo / ph_max` | numérico | Especificação de pH da família |
| `familias_produto.csv` | `densidade_min / _alvo / _max` | numérico | Especificação de densidade em g/cm³ |
| `familias_produto.csv` | `agitacao_magnetica_aplicavel` | booleano | Falso para o desinfetante (produto límpido) |
| `familias_produto.csv` | `excecao_centrifugacao` | texto | Regra de aceitação por exceção, quando existe |
| `familias_produto.csv` | `fonte_faixa_ph` | texto | [LIT] literatura/regulação ou [EST] estimativa; detalhe em FONTES.md |

## `dados_longo.csv`: data da amostra

Gerado pelo `src/02_preparar_dados.py`. `data_amostra` é derivada: no Estágio 1 é `data_inicio_teste`; no Estágio 2 é `data_inicio_teste + tempo_dias`; no Estágio 3 é `data_inicio_teste + 30 + tempo_dias`, porque o funil é sequencial e o Estágio 3 só começa depois do portão de 30 dias do Estágio 2. (Antes desta revisão, o Estágio 3 usava `data_inicio_teste + tempo_dias`, e as janelas dos dois estágios coincidiam. A mudança altera apenas essa coluna, nas linhas do Estágio 3; nenhum julgamento contra a spec muda, pois o único ensaio com spec versionada, `delta_e_liberacao`, é do Estágio 1.)
