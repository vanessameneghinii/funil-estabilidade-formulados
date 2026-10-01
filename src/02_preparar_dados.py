"""
02_preparar_dados.py: preparacao e qualidade do dado
=====================================================

Transforma os sete arquivos de `data/` em duas saidas consumiveis pelos scripts
seguintes, e produz o diagnostico de qualidade do dado.

Saidas:
  data/dados_longo.csv           formato longo, uma linha por medicao, ja julgada
                                 contra a especificacao VIGENTE na data da amostra
  data/features_por_lote.csv     uma linha por lote, com prefixo por momento de
                                 disponibilidade (d0_, e2_, d7_) e o alvo
  output/qualidade_dado.json     todos os numeros do diagnostico
  output/figures/01_vies_instrumento.png

Principios que guiam o script (e que valem a leitura antes do codigo):

1. NENHUM LIMITE E ESCRITO EM CODIGO. Todos os criterios vem de
   `spec_master.csv`. Se a especificacao muda, muda o CSV, nao o script. Isso e
   o oposto do que costuma acontecer em planilha de laboratorio, onde o limite
   vive dentro da formula da celula.

2. JULGAMENTO PELA SPEC VIGENTE NA DATA DA AMOSTRA, nao pela spec atual. A
   `spec_master` tem vigencia (`vigente_de` / `vigente_ate`), e a tolerancia de
   cor na liberacao foi revisada em 2024-10-01 (de dE00 2,00 para 1,50). Julgar
   um lote de maio de 2024 pela spec de hoje seria reescrever a historia do
   controle de qualidade. O script mede quantos lotes isso afetaria.

3. MEDICAO INVALIDA NAO E REPROVACAO. Um pH de 48,70 nao e um lote fora de
   especificacao: e uma medicao que nao existe. A conduta correta e invalidar e
   repetir, nunca julgar. O script separa `julgavel` de `oos`, o que espelha a
   logica do FDA Guidance sobre resultados fora de especificacao.

4. OUTLIER, OOS E OOT SAO TRES COISAS DIFERENTES, em tres colunas diferentes.
   Outlier e um valor atipico frente aos seus pares; OOS e violacao de
   especificacao; OOT e desvio de tendencia. Um valor pode ser qualquer
   combinacao dos tres.

5. O GABARITO NAO E VARIAVEL. `gabarito_erros_injetados.csv` e usado APENAS para
   medir o desempenho do detector. Se ele entrar como feature em qualquer
   modelo, o projeto perde o sentido.

Uso:
    python src/02_preparar_dados.py
    DATA_DIR=data OUT_DIR=output python src/02_preparar_dados.py
"""

from __future__ import annotations

import json
import os
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pandera.pandas as pa
from scipy.stats import mannwhitneyu
from sklearn.metrics import cohen_kappa_score

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data"))
OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "output"))
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Faixas de plausibilidade fisica. Nao sao especificacao: sao o que a grandeza
# pode ser. pH fora de [0, 14] nao existe; densidade de 10 g/cm3 seria mais densa
# que chumbo. Violar isto significa erro de registro, nunca produto ruim.
LIMITES_FISICOS = {
    "ph": (0.0, 14.0),
    "densidade_g_cm3": (0.5, 2.0),
    "delta_e_liberacao": (0.0, 100.0),
    "delta_e_estabilidade": (0.0, 100.0),
    "delta_e_estabilidade_luz": (0.0, 100.0),
}

LIMIAR_MAD = 3.5          # z-score modificado (Iglewicz & Hoaglin, 1993)
FATOR_TUKEY = 1.5         # multiplicador do IQR (cerca de Q1-1,5*IQR a Q3+1,5*IQR)
ALFA = 0.05               # nivel para o teste de vies por instrumento

resumo: dict = {}

# =========================================================================
# 1. Carga, com validacao de schema no limite de ingestao
# =========================================================================
# O schema valida ESTRUTURA (coluna existe, tipo certo, categoria pertence ao
# conjunto esperado); nunca a PLAUSIBILIDADE FISICA do valor medido. As
# medicoes fisicamente impossiveis (pH 48,70) sao intencionais: sao os erros de
# laboratorio injetados que a Secao 5 existe para detectar. Se o schema as
# rejeitasse aqui, o script falharia exatamente no dado que ele foi escrito
# para diagnosticar. A fronteira e clara: schema pega CSV malformado (coluna
# ausente, tipo errado, categoria desconhecida, ex.: um LIMS que exportou
# "Aprovada" em vez de "Aprovado"); a logica de negocio das secoes 5 a 10 pega
# medicao ruim. Confundir as duas transformaria o diagnostico de qualidade do
# DADO em erro de qualidade do SCRIPT.
ESQUEMA_ESTAGIO1 = pa.DataFrameSchema({
    "lote": pa.Column(str, unique=True, nullable=False),
    "data_inicio_teste": pa.Column("datetime64[ns]", nullable=False),
    "produto_familia": pa.Column(str, nullable=False),
    "produto_sigla": pa.Column(str, nullable=False),
    "fornecedor_tensoativo": pa.Column(str, pa.Check.isin(["FOR-A", "FOR-B", "FOR-C"])),
    "ph": pa.Column(float, nullable=False),
    "densidade_g_cm3": pa.Column(float, nullable=False),
    "delta_e_liberacao": pa.Column(float, nullable=False),
    "aspecto_score": pa.Column(int, pa.Check.isin(range(5)), nullable=False),
    "cor_score": pa.Column(int, pa.Check.isin(range(5)), nullable=False),
    "odor_conforme": pa.Column(bool, nullable=False),
    "estufa50_score": pa.Column(int, pa.Check.isin(range(5)), nullable=False),
    "centrifugacao_score": pa.Column(int, pa.Check.isin(range(5)), nullable=False),
    # NULL e valido aqui: agitacao magnetica nao se aplica ao desinfetante
    "agitacao_score": pa.Column(float, pa.Check.isin(list(range(5))), nullable=True),
    "instrumento_ph": pa.Column(str, pa.Check.isin(["PH-01", "PH-02"])),
    "status_estagio1": pa.Column(str, pa.Check.isin(["Aprovado", "Reprovado"]), nullable=False),
}, strict=False, coerce=False)

ESQUEMA_ESTABILIDADE = pa.DataFrameSchema({
    "lote": pa.Column(str, nullable=False),
    "produto_familia": pa.Column(str, nullable=False),
    # Preliminar usa 1 condicao de choque termico; acelerada usa as 4 de armazenamento
    "condicao": pa.Column(str, pa.Check.isin(
        ["Choque Termico 5C/40C", "Ambiente Escuro 25C", "Estufa 40C",
         "Geladeira 5C", "Luz Solar"])),
    "tempo_dias": pa.Column(int, pa.Check.ge(0), nullable=False),
    "ph": pa.Column(float, nullable=False),
    "densidade_g_cm3": pa.Column(float, nullable=False),
    "delta_e_estabilidade": pa.Column(float, nullable=False),
    "oos_flag": pa.Column(bool, nullable=False),
}, strict=False, coerce=False)

ESQUEMA_SPEC = pa.DataFrameSchema({
    "produto_familia": pa.Column(str, nullable=False),
    "vigente_de": pa.Column("datetime64[ns]", nullable=False),
    "versao_spec": pa.Column(str, nullable=False),
    "ensaio": pa.Column(str, nullable=False),
    "criterio_tipo": pa.Column(str, pa.Check.isin(["faixa", "max", "booleano"])),
}, strict=False, coerce=False)

ESQUEMA_FAMILIAS = pa.DataFrameSchema({
    "sigla": pa.Column(str, unique=True, nullable=False),
    "produto_familia": pa.Column(str, unique=True, nullable=False),
    "classificacao_anvisa": pa.Column(str, pa.Check.isin(["Risco 1", "Risco 2"])),
    "ph_min": pa.Column(float), "ph_alvo": pa.Column(float), "ph_max": pa.Column(float),
}, strict=False, coerce=False)

ESQUEMA_FUNIL = pa.DataFrameSchema({
    "lote": pa.Column(str, unique=True, nullable=False),
    "status_estagio1": pa.Column(str, pa.Check.isin(["Aprovado", "Reprovado"])),
    "sobreviveu_90d": pa.Column(bool, nullable=False),
}, strict=False, coerce=False)

ESQUEMA_GABARITO = pa.DataFrameSchema({
    "lote": pa.Column(str, nullable=False),
    "estagio": pa.Column(int, pa.Check.isin([1, 2, 3])),
    "parametro": pa.Column(str, nullable=False),
    "tipo_erro": pa.Column(str, pa.Check.isin(
        ["decimal_deslocado", "replicata_trocada", "sonda_descalibrada"])),
    "valor_registrado": pa.Column(float, nullable=False),
    "valor_verdadeiro": pa.Column(float, nullable=False),
}, strict=False, coerce=False)

ESQUEMA_DUPLICADAS = pa.DataFrameSchema({
    "lote": pa.Column(str, nullable=False),
    "ensaio": pa.Column(str, nullable=False),
    "escore_analista_1": pa.Column(int, pa.Check.isin(range(5))),
    "escore_analista_2": pa.Column(int, pa.Check.isin(range(5))),
}, strict=False, coerce=False)


def carregar_validado(caminho: pathlib.Path, esquema: pa.DataFrameSchema,
                      **kwargs_leitura) -> pd.DataFrame:
    """Le um CSV e valida contra o schema, reportando TODAS as violacoes de
    uma vez (lazy=True) em vez de parar na primeira. Falha antes de qualquer
    calculo: o objetivo e nunca propagar um NaN silencioso ate um resultado
    tres secoes depois."""
    df = pd.read_csv(caminho, **kwargs_leitura)
    try:
        return esquema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as erro:
        resumo = erro.failure_cases[["column", "check", "failure_case"]].head(10)
        raise SystemExit(
            f"\nSCHEMA INVALIDO em {caminho.name}: corrigir a origem do dado, "
            f"nao ajustar o schema para aceitar:\n{resumo.to_string(index=False)}\n"
            f"({len(erro.failure_cases)} violacoes no total)"
        ) from erro


e1 = carregar_validado(DATA_DIR / "estagio1_teste_inicial.csv", ESQUEMA_ESTAGIO1,
                       parse_dates=["data_inicio_teste"])
e2 = carregar_validado(DATA_DIR / "estagio2_estabilidade_preliminar.csv", ESQUEMA_ESTABILIDADE)
e3 = carregar_validado(DATA_DIR / "estagio3_estabilidade_acelerada.csv", ESQUEMA_ESTABILIDADE)
spec = carregar_validado(DATA_DIR / "spec_master.csv", ESQUEMA_SPEC,
                         parse_dates=["vigente_de", "vigente_ate"])
familias = carregar_validado(DATA_DIR / "familias_produto.csv", ESQUEMA_FAMILIAS)
duplicadas = carregar_validado(DATA_DIR / "avaliacao_duplicada_analistas.csv", ESQUEMA_DUPLICADAS)
gabarito = carregar_validado(DATA_DIR / "gabarito_erros_injetados.csv", ESQUEMA_GABARITO)
funil = carregar_validado(DATA_DIR / "funil_lotes.csv", ESQUEMA_FUNIL)

# `vigente_ate` vazio significa "ainda vigente". Preencher com data distante
# permite comparar com desigualdade, sem tratar NaN em toda condicao.
spec["vigente_ate"] = spec.vigente_ate.fillna(pd.Timestamp("2099-12-31"))

# =========================================================================
# 2. Data da amostra
# =========================================================================
# O Estagio 1 traz a data do ensaio. Os estagios 2 e 3 trazem apenas o tempo
# decorrido, logo a data da amostra e derivada. E ela que decide qual versao da
# spec se aplica.
data_lote = e1.set_index("lote").data_inicio_teste
e1["data_amostra"] = e1.data_inicio_teste
# O funil e sequencial: o Estagio 3 so comeca depois do portao do Estagio 2
# (ultima leitura do E2 = 30 dias). Somar so `tempo_dias` colocava as janelas
# dos dois estagios no mesmo dia. O deslocamento nao altera nenhum julgamento:
# o unico ensaio cuja spec muda de versao (delta_e_liberacao) e do Estagio 1.
dias_portao_e2 = int(e2.tempo_dias.max())
e2["data_amostra"] = e2.lote.map(data_lote) + pd.to_timedelta(e2.tempo_dias, unit="D")
e3["data_amostra"] = e3.lote.map(data_lote) + pd.to_timedelta(dias_portao_e2 + e3.tempo_dias, unit="D")

# =========================================================================
# 3. Formato longo unificado
# =========================================================================
# O Estagio 1 chega em formato largo (um lote por linha, um ensaio por coluna),
# como a planilha de bancada. Os estagios 2 e 3 chegam em formato longo por
# (lote x condicao x tempo). Para julgar tudo com a mesma regra, unifica-se em
# formato longo: uma linha por MEDICAO.
MAPA_DESCRITIVO = {
    "aspecto_score": "aspecto_desc",
    "cor_score": "cor_desc",
    "estufa50_score": "estufa50_desc",
    "centrifugacao_score": "centrifugacao_desc",
    "agitacao_score": "agitacao_desc",
    "odor_conforme": "odor_desc",
}
CONTEXTO = ["lote", "produto_familia", "estagio", "condicao", "tempo_dias",
            "data_amostra", "analista", "instrumento_ph"]


def empilhar(df: pd.DataFrame, ensaios: list[str]) -> pd.DataFrame:
    """Converte colunas de ensaio em linhas, preservando o contexto da medicao."""
    blocos = []
    for ensaio in ensaios:
        if ensaio not in df.columns:
            continue
        bloco = df.reindex(columns=CONTEXTO).copy()
        bloco["ensaio"] = ensaio
        coluna = df[ensaio]
        # Atributo booleano (odor) entra como 1 = conforme, 0 = nao conforme,
        # para caber na mesma coluna numerica dos demais ensaios.
        bloco["valor"] = (coluna.astype(float) if coluna.dtype == bool
                          else pd.to_numeric(coluna, errors="coerce"))
        descritivo = MAPA_DESCRITIVO.get(ensaio)
        bloco["descritivo"] = df[descritivo] if descritivo in df.columns else ""
        blocos.append(bloco)
    return pd.concat(blocos, ignore_index=True)


e1_ctx = e1.assign(estagio=1, condicao="Teste Inicial", tempo_dias=0)
e2_ctx = e2.assign(analista=pd.NA, instrumento_ph=pd.NA)
e3_ctx = e3.assign(analista=pd.NA, instrumento_ph=pd.NA)

ENSAIOS_E1 = ["ph", "densidade_g_cm3", "delta_e_liberacao", "aspecto_score",
              "cor_score", "odor_conforme", "estufa50_score",
              "centrifugacao_score", "agitacao_score"]
ENSAIOS_EST = ["ph", "densidade_g_cm3", "delta_e_estabilidade",
               "aspecto_score", "cor_score", "odor_conforme"]

longo = pd.concat([empilhar(e1_ctx, ENSAIOS_E1),
                   empilhar(e2_ctx, ENSAIOS_EST),
                   empilhar(e3_ctx, ENSAIOS_EST)], ignore_index=True)

# Ensaio nao aplicavel (agitacao magnetica no desinfetante limpido) chega como
# valor ausente: remove-se, porque "nao medido" nao e "medido e conforme".
longo = longo[longo.valor.notna()].reset_index(drop=True)

# Sob luz solar, a alteracao de cor responde a outra pergunta (fotoestabilidade)
# e tem limite proprio na spec. Renomear o ensaio faz a juncao seguinte escolher
# o criterio certo sem nenhum "if condicao == ..." espalhado pelo codigo.
luz = (longo.ensaio == "delta_e_estabilidade") & (longo.condicao == "Luz Solar")
longo.loc[luz, "ensaio"] = "delta_e_estabilidade_luz"

resumo["n_medicoes"] = int(len(longo))
resumo["n_lotes"] = int(longo.lote.nunique())

# =========================================================================
# 4. Juncao com a spec vigente na data da amostra
# =========================================================================
# Juncao "as-of": cada medicao encontra a linha da spec cuja janela de vigencia
# contem a data da amostra. Sem isso, um lote de maio de 2024 seria julgado pela
# tolerancia de cor apertada em outubro de 2024.
juncao = longo.merge(spec, on=["produto_familia", "ensaio"], how="left")
na_vigencia = (juncao.data_amostra >= juncao.vigente_de) & (juncao.data_amostra <= juncao.vigente_ate)
sem_criterio = juncao.versao_spec.isna()
m = juncao[na_vigencia | sem_criterio].reset_index(drop=True)

# Se a spec tiver janelas sobrepostas, uma medicao casaria com duas linhas e
# o mesmo resultado seria julgado duas vezes. A assercao protege disso.
assert len(m) == len(longo), (
    f"juncao por vigencia gerou {len(m)} linhas para {len(longo)} medicoes: "
    "ha janelas de vigencia sobrepostas ou lacunas na spec_master")
resumo["medicoes_sem_criterio_na_spec"] = int(sem_criterio.sum())
resumo["versoes_de_spec_aplicadas"] = (
    m.groupby("ensaio").versao_spec.nunique().loc[lambda s: s > 1].to_dict())

# =========================================================================
# 5. Validacao de plausibilidade fisica
# =========================================================================
m["valor_impossivel"] = False
for ensaio, (piso, teto) in LIMITES_FISICOS.items():
    alvo = m.ensaio == ensaio
    m.loc[alvo, "valor_impossivel"] = ~m.loc[alvo, "valor"].between(piso, teto)
resumo["medicoes_fisicamente_impossiveis"] = int(m.valor_impossivel.sum())
resumo["lotes_com_medicao_impossivel"] = int(m[m.valor_impossivel].lote.nunique())

# =========================================================================
# 6. Julgamento contra a especificacao
# =========================================================================
lim_min = pd.to_numeric(m.limite_min, errors="coerce")
lim_max = pd.to_numeric(m.limite_max, errors="coerce")

abaixo = lim_min.notna() & (m.valor < lim_min)
acima = lim_max.notna() & (m.valor > lim_max)
atributo_nc = (m.criterio_tipo == "booleano") & (m.valor == 0)

# `julgavel` separa "posso decidir sobre este resultado" de "este resultado esta
# fora de especificacao". Medicao impossivel e sem criterio na spec nao se julga.
m["julgavel"] = (~m.valor_impossivel) & m.criterio_tipo.notna()
m["oos"] = m.julgavel & (abaixo | acima | atributo_nc)
m["motivo"] = np.select(
    [m.valor_impossivel, ~m.criterio_tipo.notna(), abaixo, acima, atributo_nc],
    ["medicao fisicamente impossivel: invalidar e repetir",
     "sem criterio declarado na spec",
     "abaixo do limite inferior", "acima do limite superior",
     "atributo nao conforme"],
    default="")

# --- 6a. A regra reconstruida reproduz a disposicao do dataset? -----------------
# Teste de sanidade do pipeline: aplicando a spec_master as medicoes do Estagio
# 1, a disposicao calculada deve coincidir com `status_estagio1`. Divergencia
# esperada apenas nos lotes com medicao impossivel, que a regra correta invalida
# em vez de julgar.
e1_long = m[m.estagio == 1]
reprova_calc = e1_long[e1_long.julgavel].groupby("lote").oos.any()
disposicao = pd.DataFrame({
    "calculada": np.where(reprova_calc, "Reprovado", "Aprovado")}, index=reprova_calc.index)
disposicao["registrada"] = disposicao.index.map(e1.set_index("lote").status_estagio1)
disposicao["tem_medicao_impossivel"] = disposicao.index.isin(
    e1_long.loc[e1_long.valor_impossivel, "lote"])
divergentes = disposicao[disposicao.calculada != disposicao.registrada]
resumo["disposicao_E1_reproduzida"] = int((disposicao.calculada == disposicao.registrada).sum())
resumo["disposicao_E1_divergente"] = int(len(divergentes))
resumo["divergencias_explicadas_por_medicao_invalida"] = int(
    divergentes.tem_medicao_impossivel.sum())

# --- 6b. Quanto custaria julgar tudo pela spec de hoje? --------------------
# Reproduz o erro comum: juntar com a spec atual e ignorar a vigencia.
spec_hoje = spec[spec.vigente_ate == pd.Timestamp("2099-12-31")]
m_hoje = longo[longo.estagio == 1].merge(
    spec_hoje.drop(columns=["vigente_de", "vigente_ate"]),
    on=["produto_familia", "ensaio"], how="left")
lmin_h = pd.to_numeric(m_hoje.limite_min, errors="coerce")
lmax_h = pd.to_numeric(m_hoje.limite_max, errors="coerce")
impossivel_h = pd.Series(False, index=m_hoje.index)
for ensaio, (piso, teto) in LIMITES_FISICOS.items():
    alvo = m_hoje.ensaio == ensaio
    impossivel_h.loc[alvo] = ~m_hoje.loc[alvo, "valor"].between(piso, teto)
oos_h = (~impossivel_h) & m_hoje.criterio_tipo.notna() & (
    (lmin_h.notna() & (m_hoje.valor < lmin_h))
    | (lmax_h.notna() & (m_hoje.valor > lmax_h))
    | ((m_hoje.criterio_tipo == "booleano") & (m_hoje.valor == 0)))
reprova_hoje = oos_h.groupby(m_hoje.lote).any()
resumo["lotes_com_disposicao_alterada_se_ignorar_vigencia"] = int(
    (reprova_hoje.reindex(reprova_calc.index) != reprova_calc).sum())

# --- 6c. Lotes aceitos por excecao declarada na spec ----------------------
resumo["lotes_aceitos_por_excecao"] = int((e1.observacoes.fillna("") != "").sum())

# =========================================================================
# 7. Deteccao de outlier
# =========================================================================
# Dois detectores univariados, ambos robustos (baseados em mediana, nao em
# media: media e desvio-padrao sao eles proprios arrastados pelo outlier que se
# quer encontrar). Comparacao dentro de cada familia de produto, porque um pH de
# 10,2 e normal no multiuso e absurdo no amaciante.
e1_num = m[(m.estagio == 1) & m.ensaio.isin(["ph", "densidade_g_cm3"])].copy()
grupo = e1_num.groupby(["produto_familia", "ensaio"]).valor

mediana = grupo.transform("median")
mad = grupo.transform(lambda s: (s - s.median()).abs().median())
# 0.6745 = quantil 0,75 da normal padrao; torna o MAD comparavel ao desvio-padrao
e1_num["z_mad"] = 0.6745 * (e1_num.valor - mediana) / mad.replace(0, np.nan)
e1_num["outlier_mad"] = e1_num.z_mad.abs() > LIMIAR_MAD

q1 = grupo.transform(lambda s: s.quantile(0.25))
q3 = grupo.transform(lambda s: s.quantile(0.75))
iqr = q3 - q1
e1_num["outlier_iqr"] = (e1_num.valor < q1 - FATOR_TUKEY * iqr) | (e1_num.valor > q3 + FATOR_TUKEY * iqr)

# --- 7a. Desempenho dos detectores contra o gabarito ---------------------
# O gabarito e usado SO aqui. Um projeto com dado real nao tem esta medida:
# e a principal vantagem epistemica de um dataset sintetico.
verdade = set(zip(gabarito.lote, gabarito.parametro))
tipo_por_par = dict(zip(zip(gabarito.lote, gabarito.parametro), gabarito.tipo_erro))
desempenho = {}
for nome, coluna in [("z-score modificado (MAD)", "outlier_mad"),
                     ("IQR de Tukey", "outlier_iqr"),
                     ("faixa fisica", "valor_impossivel")]:
    detectados = set(zip(e1_num.loc[e1_num[coluna], "lote"],
                         e1_num.loc[e1_num[coluna], "ensaio"]))
    vp = len(detectados & verdade)
    fp = len(detectados - verdade)
    fn = len(verdade - detectados)
    por_tipo = {}
    for tipo in sorted(gabarito.tipo_erro.unique()):
        alvo = {par for par, t in tipo_por_par.items() if t == tipo}
        por_tipo[tipo] = round(len(detectados & alvo) / len(alvo), 3) if alvo else None
    desempenho[nome] = dict(
        verdadeiros_positivos=vp, falsos_positivos=fp, falsos_negativos=fn,
        recall=round(vp / (vp + fn), 3) if vp + fn else None,
        precisao=round(vp / (vp + fp), 3) if vp + fp else None,
        recall_por_tipo_de_erro=por_tipo)
resumo["desempenho_detectores"] = desempenho
resumo["erros_injetados_por_tipo"] = gabarito.tipo_erro.value_counts().to_dict()

# --- 7b. Ponto atipico nas series de estabilidade ------------------------
# Duas armadilhas reais, nesta ordem:
#
# (1) Aplicar um filtro de ponto atipico (Hampel, z-score) DIRETO sobre uma
#     serie de estabilidade nao funciona: a serie deriva por construcao, e o
#     filtro sinaliza as pontas da tendencia, que sao o comportamento
#     esperado. Aplicado a esta serie, esse metodo gera 220 sinalizacoes
#     espurias.
#
# (2) Remover a tendencia e filtrar o residuo tambem nao resolve AQUI: cada
#     serie tem 5 pontos e dois graus de liberdade vao para a reta, de modo que
#     o MAD dos residuos e um estimador de escala pessimo. Tentado: 451
#     sinalizacoes em 8.360 medicoes, pior que o metodo ingenuo.
#
# O que funciona com series curtas e comparar ENTRE LOTES no MESMO ponto de
# tempo: a referencia passa a ser a distribuicao dos outros lotes da mesma
# familia, na mesma condicao, no mesmo dia de avaliacao, onde ha dezenas de
# observacoes em vez de cinco. E a abordagem de intervalo de tolerancia por
# ponto de tempo, usada para deteccao de fora de tendencia (OOT) em estudos de
# estabilidade.
#
# Aqui nao existe gabarito: nenhum erro foi injetado nos estagios 2 e 3. O
# resultado sao CANDIDATOS a revisao, e e assim que devem ser reportados.
est = m[(m.estagio != 1)
        & m.ensaio.isin(["ph", "densidade_g_cm3", "delta_e_estabilidade",
                         "delta_e_estabilidade_luz"])].copy()
celula = est.groupby(["produto_familia", "condicao", "ensaio", "tempo_dias"]).valor
mediana_celula = celula.transform("median")
mad_celula = celula.transform(lambda s: (s - s.median()).abs().median())
est["z_entre_lotes"] = (0.6745 * (est.valor - mediana_celula)
                        / mad_celula.replace(0, np.nan))
est["candidato_revisao"] = est.z_entre_lotes.abs() > LIMIAR_MAD

resumo["oot_candidatos_a_revisao"] = int(est.candidato_revisao.fillna(False).sum())
resumo["oot_medicoes_avaliadas"] = int(est.z_entre_lotes.notna().sum())
resumo["oot_taxa_de_sinalizacao"] = round(
    float(est.candidato_revisao.fillna(False).mean()), 4)
resumo["oot_lotes_com_pelo_menos_um_candidato"] = int(
    est.loc[est.candidato_revisao.fillna(False), "lote"].nunique())

# =========================================================================
# 8. Vies sistematico por instrumento
# =========================================================================
# O erro mais difícil do dataset: uma sonda com offset. Cada valor individual e
# plausivel, entao nenhum detector de outlier univariado o encontra. Aparece
# comparando os dois instrumentos MES A MES, sobre o residuo em relacao ao alvo
# da familia (o residuo remove o efeito de familia, que e muito maior que o
# offset procurado).
alvo_ph = familias.set_index("produto_familia").ph_alvo
base = e1[e1.ph.between(*LIMITES_FISICOS["ph"])].copy()
base["residuo_ph"] = base.ph - base.produto_familia.map(alvo_ph)
base["mes"] = base.data_inicio_teste.dt.to_period("M")

por_mes = []
for mes, bloco in base.groupby("mes"):
    a = bloco.loc[bloco.instrumento_ph == "PH-01", "residuo_ph"]
    b = bloco.loc[bloco.instrumento_ph == "PH-02", "residuo_ph"]
    if len(a) >= 3 and len(b) >= 3:
        p = mannwhitneyu(b, a, alternative="two-sided").pvalue
    else:
        p = np.nan
    por_mes.append(dict(mes=str(mes), n_ph01=len(a), n_ph02=len(b),
                        mediana_ph01=a.median(), mediana_ph02=b.median(),
                        diferenca=b.median() - a.median(), p_valor=p))
por_mes = pd.DataFrame(por_mes)
# Correcao de Bonferroni: 18 meses testados, entao o limiar por teste e alfa/18.
# Sem isso, um mes "significativo" em 18 e o resultado esperado do puro acaso.
testados = por_mes.p_valor.notna().sum()
por_mes["significativo"] = por_mes.p_valor < (ALFA / max(testados, 1))
suspeitos = por_mes[por_mes.significativo]

# --- 8a. Varredura em janela de tres meses --------------------------------
# O teste mes a mes tem pouca potencia: sao cerca de 8 lotes por instrumento por
# mes. Agrupar tres meses consecutivos aumenta a potencia ao custo de resolucao
# temporal: o metodo passa a localizar o periodo com precisao de trimestre, nao
# de mes. Reportar os dois preserva essa diferenca de resolucao: o mensal tem alta
# especificidade, o trimestral tem alta sensibilidade.
meses = por_mes.mes.tolist()
linhas_janela = []
for i in range(len(meses) - 2):
    span = meses[i:i + 3]
    bloco = base[base.mes.astype(str).isin(span)]
    a = bloco.loc[bloco.instrumento_ph == "PH-01", "residuo_ph"]
    b = bloco.loc[bloco.instrumento_ph == "PH-02", "residuo_ph"]
    p = (mannwhitneyu(b, a, alternative="two-sided").pvalue
         if min(len(a), len(b)) >= 5 else np.nan)
    linhas_janela.append(dict(janela=f"{span[0]} a {span[-1]}", primeiro_mes=span[0],
                              ultimo_mes=span[-1], n_ph01=len(a), n_ph02=len(b),
                              diferenca=b.median() - a.median(), p_valor=p))
janelas = pd.DataFrame(linhas_janela)
n_janelas = int(janelas.p_valor.notna().sum())
janelas["significativo"] = janelas.p_valor < (ALFA / max(n_janelas, 1))
sinalizadas = janelas[janelas.significativo]

# Span final: uniao dos meses cobertos pelas janelas sinalizadas.
meses_no_span = sorted({mes for _, linha in sinalizadas.iterrows()
                        for mes in meses[meses.index(linha.primeiro_mes):
                                         meses.index(linha.ultimo_mes) + 1]})
dentro_span = base.mes.astype(str).isin(meses_no_span)
offset_span = (base.loc[dentro_span & (base.instrumento_ph == "PH-02"), "residuo_ph"].median()
               - base.loc[dentro_span & (base.instrumento_ph == "PH-01"), "residuo_ph"].median()
               ) if meses_no_span else None

resumo["vies_instrumento"] = dict(
    meses_testados=int(testados),
    limiar_bonferroni_mensal=round(ALFA / max(testados, 1), 5),
    meses_sinalizados_teste_mensal=suspeitos.mes.tolist(),
    offset_estimado_teste_mensal=round(float(suspeitos.diferenca.median()), 3) if len(suspeitos) else None,
    janelas_de_3_meses_testadas=n_janelas,
    janelas_sinalizadas=sinalizadas.janela.tolist(),
    span_recuperado=[meses_no_span[0], meses_no_span[-1]] if meses_no_span else None,
    offset_estimado_no_span=round(float(offset_span), 3) if offset_span is not None else None)

# =========================================================================
# 9. Concordancia entre analistas
# =========================================================================
# Kappa PONDERADO (quadratico) porque o escore e ordinal: discordar 0 contra 1 e
# menos grave que discordar 0 contra 3, e o kappa simples trataria as duas como
# um erro igual.
resumo["kappa_quadratico"] = {
    ensaio: round(cohen_kappa_score(bloco.escore_analista_1, bloco.escore_analista_2,
                                    weights="quadratic"), 3)
    for ensaio, bloco in duplicadas.groupby("ensaio")}
resumo["n_reavaliacoes"] = int(len(duplicadas))
resumo["taxa_de_discordancia"] = round(
    float((duplicadas.escore_analista_1 != duplicadas.escore_analista_2).mean()), 3)

# =========================================================================
# 10. Reprovacoes atribuiveis a erro de laboratorio
# =========================================================================
# A pergunta de negocio da deteccao de outlier: quantos lotes foram reprovados
# por causa do erro, e nao por causa do produto? Rejulga-se o Estagio 1 com os
# valores verdadeiros e compara-se a disposicao.
corrigido = longo[longo.estagio == 1].merge(
    gabarito.rename(columns={"parametro": "ensaio"})[["lote", "ensaio", "valor_verdadeiro"]],
    on=["lote", "ensaio"], how="left")
corrigido["valor"] = corrigido.valor_verdadeiro.fillna(corrigido.valor)
mc = corrigido.merge(spec, on=["produto_familia", "ensaio"], how="left")
mc = mc[((mc.data_amostra >= mc.vigente_de) & (mc.data_amostra <= mc.vigente_ate))
        | mc.versao_spec.isna()]
lmin_c = pd.to_numeric(mc.limite_min, errors="coerce")
lmax_c = pd.to_numeric(mc.limite_max, errors="coerce")
oos_c = mc.criterio_tipo.notna() & (
    (lmin_c.notna() & (mc.valor < lmin_c))
    | (lmax_c.notna() & (mc.valor > lmax_c))
    | ((mc.criterio_tipo == "booleano") & (mc.valor == 0)))
reprova_corrigida = oos_c.groupby(mc.lote).any()

comparacao = pd.DataFrame({
    "registrada": e1.set_index("lote").status_estagio1 == "Reprovado",
    "com_valor_verdadeiro": reprova_corrigida})
afetados = comparacao.loc[sorted(set(gabarito.lote))]
resumo["lotes_com_erro_injetado"] = int(len(afetados))
resumo["reprovados_indevidamente"] = int(
    (afetados.registrada & ~afetados.com_valor_verdadeiro).sum())
resumo["aprovados_indevidamente"] = int(
    (~afetados.registrada & afetados.com_valor_verdadeiro).sum())

# =========================================================================
# 11. Tabela de features por lote
# =========================================================================
# Prefixo = MOMENTO em que a informacao passa a existir. E o que impede
# vazamento temporal: o script 04 escolhe explicitamente o horizonte de decisao
# que quer testar, em vez de misturar informacao de epocas diferentes.
#   d0_  disponivel no dia do Teste Inicial
#   e2_  disponivel ao fim da Estabilidade Preliminar (cerca de 30 dias)
#   d7_  disponivel no dia 7 da Estabilidade Acelerada (cerca de 37 dias)
COLS_D0 = ["ph", "densidade_g_cm3", "delta_e_liberacao", "aspecto_score", "cor_score",
           "odor_conforme", "estufa50_score", "centrifugacao_score", "agitacao_score"]
features = e1[["lote", "data_inicio_teste", "produto_familia", "produto_sigla",
               "fornecedor_tensoativo", "analista", "instrumento_ph"] + COLS_D0].copy()
features = features.rename(columns={c: f"d0_{c}" for c in COLS_D0})
features["d0_odor_conforme"] = features.d0_odor_conforme.astype(int)
features = features.merge(
    familias[["produto_familia", "classificacao_anvisa", "ph_alvo", "densidade_alvo"]],
    on="produto_familia", how="left")
# Residuos em relacao ao alvo da familia: comparaveis entre familias, ao
# contrario dos valores absolutos.
features["d0_residuo_ph"] = features.d0_ph - features.ph_alvo
features["d0_residuo_densidade"] = features.d0_densidade_g_cm3 - features.densidade_alvo

# Estagio 2: deriva sob choque termico ao fim dos 30 dias
e2_30 = e2[e2.tempo_dias == 30].set_index("lote")
features["e2_delta_ph_30d"] = features.lote.map(e2_30.ph) - features.d0_ph
features["e2_delta_densidade_30d"] = (features.lote.map(e2_30.densidade_g_cm3)
                                      - features.d0_densidade_g_cm3)
features["e2_delta_e_30d"] = features.lote.map(e2_30.delta_e_estabilidade)
features["e2_aspecto_score_30d"] = features.lote.map(e2_30.aspecto_score)

# Estagio 3: primeira leitura (dia 7) em cada condicao de armazenamento
d7 = e3[e3.tempo_dias == 7].pivot_table(
    index="lote", columns="condicao",
    values=["ph", "densidade_g_cm3", "delta_e_estabilidade"])
d7.columns = [f"d7_{par}_{cond}".replace(" ", "_").replace("delta_e_estabilidade", "delta_e")
              for par, cond in d7.columns]
features = features.merge(d7.reset_index(), on="lote", how="left")

# Alvo. Restringe-se aos lotes que chegaram ao Estagio 3: prever o desfecho de
# quem nunca entrou no estudo nao e a pergunta (e o proprio funil ja decidiu).
alvo = funil[["lote", "status_estagio1", "status_estagio2", "status_estagio3_90d",
              "fotoestabilidade_90d", "estagio_final", "sobreviveu_90d"]]
features = features.merge(alvo, on="lote", how="left")
features["chegou_ao_estagio3"] = features.status_estagio3_90d.notna()
resumo["features"] = dict(
    n_colunas=int(features.shape[1]), n_lotes=int(len(features)),
    n_lotes_no_estagio3=int(features.chegou_ao_estagio3.sum()),
    taxa_sobrevivencia_entre_os_que_chegaram=round(
        float(features.loc[features.chegou_ao_estagio3, "sobreviveu_90d"].mean()), 3))

# =========================================================================
# 12. Figura: vies por instrumento
# =========================================================================
plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 300, "font.size": 8,
    "axes.titlesize": 8.5, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlelocation": "left", "figure.autolayout": False,
})
COR = {"PH-01": "#3B7EA1", "PH-02": "#C4531A"}

fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.4, 3.0),
                                 gridspec_kw={"width_ratios": [2.1, 1]})

x = np.arange(len(por_mes))
for inst, coluna in [("PH-01", "mediana_ph01"), ("PH-02", "mediana_ph02")]:
    ax_a.plot(x, por_mes[coluna], marker="o", ms=3.2, lw=1.4, color=COR[inst], label=inst)
for xi in [i for i, mes in enumerate(por_mes.mes) if mes in meses_no_span]:
    ax_a.axvspan(xi - 0.5, xi + 0.5, color="#C4531A", alpha=0.08, lw=0)
for xi in x[por_mes.significativo.to_numpy()]:
    ax_a.axvspan(xi - 0.5, xi + 0.5, color="#C4531A", alpha=0.22, lw=0)
ax_a.axhline(0, color="#8C8C8C", lw=0.8, zorder=0)
ax_a.set_xticks(x)
ax_a.set_xticklabels([m[2:] for m in por_mes.mes], rotation=90)
ax_a.set_xlabel("Mês do ensaio (ano-mês)")
ax_a.set_ylabel("Resíduo de pH (medido − alvo)")
ax_a.set_title("Sombra clara: span recuperado pela varredura trimestral.\n"
                "Sombra escura: mês sinalizado pelo teste mensal")
ax_a.legend(frameon=False, loc="upper left")

dentro = dentro_span
dados_box, rotulos, cores = [], [], []
for inst in ["PH-01", "PH-02"]:
    for janela, nome in [(dentro, "na janela"), (~dentro, "fora")]:
        dados_box.append(base.loc[(base.instrumento_ph == inst) & janela, "residuo_ph"].to_numpy())
        rotulos.append(f"{inst}\n{nome}")
        cores.append(COR[inst])
caixas = ax_b.boxplot(dados_box, tick_labels=rotulos, widths=0.6,
                      patch_artist=True, medianprops=dict(color="black", lw=1.2),
                      flierprops=dict(marker="o", ms=2.5, mfc="none", mec="#8C8C8C"))
for caixa, cor in zip(caixas["boxes"], cores):
    caixa.set(facecolor=cor, alpha=0.35, edgecolor=cor, lw=1.0)
ax_b.axhline(0, color="#8C8C8C", lw=0.8, zorder=0)
ax_b.set_ylabel("Resíduo de pH")
offset = resumo["vies_instrumento"]["offset_estimado_no_span"]
ax_b.set_title(f"Offset estimado da PH-02: {offset:+.2f} de pH" if offset is not None
               else "Nenhuma janela sinalizada")

fig.tight_layout(pad=0.6)
fig.savefig(FIG_DIR / "01_vies_instrumento.png", bbox_inches="tight")
plt.close(fig)

# =========================================================================
# 13. Gravacao
# =========================================================================
COLS_LONGO = ["lote", "produto_familia", "estagio", "condicao", "tempo_dias",
              "data_amostra", "ensaio", "valor", "descritivo", "analista",
              "instrumento_ph", "versao_spec", "criterio_tipo", "limite_min",
              "limite_max", "excecao_permitida", "valor_impossivel", "julgavel",
              "oos", "motivo"]
m[COLS_LONGO].to_csv(DATA_DIR / "dados_longo.csv", index=False, encoding="utf-8")
features.to_csv(DATA_DIR / "features_por_lote.csv", index=False, encoding="utf-8")
por_mes.to_csv(OUT_DIR / "vies_instrumento_por_mes.csv", index=False, encoding="utf-8")
janelas.to_csv(OUT_DIR / "vies_instrumento_janelas.csv", index=False, encoding="utf-8")
with open(OUT_DIR / "qualidade_dado.json", "w", encoding="utf-8") as arquivo:
    json.dump(resumo, arquivo, ensure_ascii=False, indent=2, default=str)

print(f"medicoes: {resumo['n_medicoes']} | OOS: {int(m.oos.sum())} "
      f"| invalidas: {resumo['medicoes_fisicamente_impossiveis']}")
print(f"disposicao do Estagio 1 reproduzida em {resumo['disposicao_E1_reproduzida']}/300 lotes "
      f"({resumo['disposicao_E1_divergente']} divergencias, "
      f"{resumo['divergencias_explicadas_por_medicao_invalida']} por medicao invalida)")
print(f"ignorar a vigencia da spec mudaria a disposicao de "
      f"{resumo['lotes_com_disposicao_alterada_se_ignorar_vigencia']} lotes")
print(f"reprovados indevidamente por erro de laboratorio: {resumo['reprovados_indevidamente']}")
print(f"vies de instrumento: teste mensal -> {resumo['vies_instrumento']['meses_sinalizados_teste_mensal']} "
      f"| varredura trimestral -> {resumo['vies_instrumento']['span_recuperado']} "
      f"| offset estimado {resumo['vies_instrumento']['offset_estimado_no_span']}")
print(f"kappa quadratico: {resumo['kappa_quadratico']}")
print(f"features: {features.shape[0]} lotes x {features.shape[1]} colunas")
