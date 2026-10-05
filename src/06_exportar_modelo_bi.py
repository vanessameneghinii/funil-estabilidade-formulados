"""
06_exportar_modelo_bi.py: exporta o modelo estrela para o Power BI
====================================================================

Consome os CSV de `data/` (saidas do 01) e produz, em `powerbi/dados_modelo/`,
as tabelas do modelo semantico, mais os valores de referencia calculados
independentemente em pandas para conferir cada medida DAX depois.

Modelo (grao de cada tabela):

  FATOS
    fMedicoes         lote x condicao x ensaio x tempo_dias        (dados_longo)
    fOcupacaoCamara   lote x condicao x dia de ocupacao de camara  (derivada)
    pLoteCausa        lote x estagio x causa de reprovacao         (ponte M:N)

  DIMENSOES
    dLote        1 linha por lote (familia e fornecedor ja desnormalizados)
    dCondicao    condicao de armazenamento / estagio
    dEnsaio      ensaio, grupo e tipo de valor
    dAnalista    analista (mais 'N/D')
    dInstrumento sonda de pH (mais 'N/D')
    dCausa       causa de reprovacao normalizada e agrupada

  dCalendario NAO e exportada: e gerada em Power Query (M), ver powerbi/M/.

Decisoes de modelagem (justificativa completa em powerbi/README_MODELO.md):
  - Colunas de texto livre (`descritivo`) e colunas redundantes com dLote
    (`produto_familia`, `estagio`, `criterio_tipo`, `excecao_permitida`) saem
    da fato: cardinalidade alta e nenhum uso analitico.
  - Nulos de chave estrangeira viram 'N/D' para evitar o membro (Blank) nos
    slicers.
  - As datas sao usadas como gravadas em `dados_longo.csv`. O 02 garante o
    funil sequencial (estagio 3 comeca apos o portao de 30 dias do estagio 2);
    este script verifica isso e falha se os estagios voltarem a se sobrepor.

Saidas:
  powerbi/dados_modelo/*.csv
  powerbi/valores_de_referencia.csv
  powerbi/referencia_mensal.csv
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import pandas as pd

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data"))
OUT_DIR = pathlib.Path(os.environ.get("BI_DIR", "powerbi"))
MODEL_DIR = OUT_DIR / "dados_modelo"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================================
# 1. Carga
# =========================================================================
dl = pd.read_csv(DATA_DIR / "dados_longo.csv", parse_dates=["data_amostra"])
fl = pd.read_csv(DATA_DIR / "funil_lotes.csv", parse_dates=["data_inicio_teste"])
fam = pd.read_csv(DATA_DIR / "familias_produto.csv")

assert fl["lote"].is_unique
assert set(dl["lote"]) == set(fl["lote"]), "lotes de dados_longo e funil_lotes divergem"

# =========================================================================
# 2. Dimensoes
# =========================================================================
# ---- dLote: funil + familia + fornecedor (merge para estrela) -----------
ORDEM_FINAL = {
    "Reprovado no Teste Inicial": 1,
    "Reprovado na Estabilidade Preliminar": 2,
    "Reprovado na Estabilidade Acelerada": 3,
    "Aprovado aos 90 dias": 4,
}
d_lote = fl.merge(
    fam[["sigla", "classificacao_anvisa", "ph_alvo", "densidade_alvo"]],
    left_on="produto_sigla", right_on="sigla", how="left", validate="m:1",
).drop(columns="sigla")
assert d_lote["ph_alvo"].notna().all()
for c in ["status_estagio2", "status_estagio3_90d", "fotoestabilidade_90d"]:
    d_lote[c] = d_lote[c].fillna("Nao avaliado")
d_lote["chegou_ao_estagio3"] = d_lote["status_estagio3_90d"].ne("Nao avaliado")
d_lote["estagio_final_ordem"] = d_lote["estagio_final"].map(ORDEM_FINAL)
assert d_lote["estagio_final_ordem"].notna().all()
d_lote = d_lote[[
    "lote", "produto_sigla", "produto_familia", "classificacao_anvisa",
    "fornecedor_tensoativo", "data_inicio_teste", "ph_alvo", "densidade_alvo",
    "status_estagio1", "status_estagio2", "status_estagio3_90d",
    "fotoestabilidade_90d", "estagio_final", "estagio_final_ordem",
    "sobreviveu_90d", "chegou_ao_estagio3",
]].sort_values("lote").reset_index(drop=True)

# ---- dCondicao -----------------------------------------------------------
d_condicao = pd.DataFrame({
    "condicao": ["Teste Inicial", "Choque Termico 5C/40C", "Ambiente Escuro 25C",
                 "Estufa 40C", "Geladeira 5C", "Luz Solar"],
    "estagio": [1, 2, 3, 3, 3, 3],
    "estagio_nome": ["1. Teste Inicial", "2. Estabilidade Preliminar"] + ["3. Estabilidade Acelerada"] * 4,
    "ordem": [1, 2, 3, 4, 5, 6],
    "exposicao_luz": [False, False, False, False, False, True],
    "ocupa_camara": [False, True, True, True, True, True],
})
assert set(dl["condicao"]) == set(d_condicao["condicao"])

# ---- dEnsaio -------------------------------------------------------------
d_ensaio = pd.DataFrame([
    ("ph", "Fisico-quimico", "numerico", "pH", 1),
    ("densidade_g_cm3", "Fisico-quimico", "numerico", "g/cm3", 2),
    ("delta_e_liberacao", "Cor", "numerico", "dE00", 3),
    ("delta_e_estabilidade", "Cor", "numerico", "dE00", 4),
    ("delta_e_estabilidade_luz", "Cor", "numerico", "dE00", 5),
    ("cor_score", "Cor", "escala 0-4", "escore", 6),
    ("aspecto_score", "Aparencia", "escala 0-4", "escore", 7),
    ("odor_conforme", "Sensorial", "booleano 0/1", "conforme", 8),
    ("estufa50_score", "Estresse fisico", "escala 0-4", "escore", 9),
    ("centrifugacao_score", "Estresse fisico", "escala 0-4", "escore", 10),
    ("agitacao_score", "Estresse fisico", "escala 0-4", "escore", 11),
], columns=["ensaio", "grupo", "tipo_valor", "unidade", "ordem"])
assert set(dl["ensaio"]) == set(d_ensaio["ensaio"])

# ---- dAnalista / dInstrumento -------------------------------------------
dl["analista"] = dl["analista"].fillna("N/D")
dl["instrumento_ph"] = dl["instrumento_ph"].fillna("N/D")
d_analista = pd.DataFrame({"analista": sorted(dl["analista"].unique())})
d_instrumento = pd.DataFrame({"instrumento_ph": sorted(dl["instrumento_ph"].unique())})

# ---- dCausa + pLoteCausa (ponte muitos-para-muitos) ----------------------
GRUPO_CAUSA = {
    "falha em estufa 50C": ("Estresse fisico", 1),
    "falha em centrifugacao": ("Estresse fisico", 2),
    "falha em agitacao magnetica": ("Estresse fisico", 3),
    "pH fora de faixa": ("Fisico-quimico", 4),
    "densidade fora de faixa": ("Fisico-quimico", 5),
    "aspecto nao conforme": ("Visual e sensorial", 6),
    "cor fora de tolerancia": ("Visual e sensorial", 7),
    "odor alterado": ("Visual e sensorial", 8),
}
ponte = []
for est in (1, 2, 3):
    col = f"causa_reprovacao_estagio{est}" if est != 3 else "causa_reprovacao_estagio3"
    s = fl.set_index("lote")[col].dropna()
    for lote, txt in s.items():
        for causa in dict.fromkeys(p.strip() for p in txt.split(";")):  # dedupe preservando ordem
            ponte.append((lote, est, causa))
p_lote_causa = pd.DataFrame(ponte, columns=["lote", "estagio", "causa"])
desconhecidas = set(p_lote_causa["causa"]) - set(GRUPO_CAUSA)
assert not desconhecidas, f"causas sem grupo: {desconhecidas}"
d_causa = pd.DataFrame(
    [(k, v[0], v[1]) for k, v in GRUPO_CAUSA.items()], columns=["causa", "grupo_causa", "ordem"]
).sort_values("ordem")
lotes_reprovados = set(fl.loc[~fl["sobreviveu_90d"], "lote"])
sem_causa = lotes_reprovados - set(p_lote_causa["lote"])
print(f"lotes reprovados: {len(lotes_reprovados)} | sem causa na ponte: {len(sem_causa)}")
assert p_lote_causa.groupby("lote")["estagio"].nunique().max() == 1, "lote com causa em >1 estagio"

# =========================================================================
# 3. Fatos
# =========================================================================
# ---- fMedicoes -----------------------------------------------------------
dl["motivo"] = dl["motivo"].fillna("conforme")
f_med = dl.merge(fl[["lote", "data_inicio_teste"]], on="lote", validate="m:1").rename(
    columns={"data_inicio_teste": "data_inicio_lote"}
)
f_med = f_med[[
    "lote", "condicao", "ensaio", "analista", "instrumento_ph",
    "data_amostra", "data_inicio_lote", "tempo_dias", "valor",
    "limite_min", "limite_max", "versao_spec",
    "julgavel", "oos", "valor_impossivel", "motivo",
]].copy()
f_med["versao_spec"] = f_med["versao_spec"].fillna("N/D")
assert len(f_med) == len(dl)

# ---- fOcupacaoCamara: 1 linha por lote x condicao x dia ocupado ----------
# janela = [inicio, inicio + tempo_max), com inicio = data_amostra - tempo_dias.
# Condicao 'Teste Inicial' e bancada (nao ocupa camara) e fica de fora.
cam = dl[dl["condicao"].isin(d_condicao.loc[d_condicao["ocupa_camara"], "condicao"])].copy()
cam["inicio"] = cam["data_amostra"] - pd.to_timedelta(cam["tempo_dias"], unit="D")
jan = cam.groupby(["lote", "condicao"]).agg(
    ini_min=("inicio", "min"), ini_max=("inicio", "max"), dias=("tempo_dias", "max")
).reset_index()
assert (jan["ini_min"] == jan["ini_max"]).all(), "inicio de janela inconsistente"

# Guarda de sequencialidade: o estagio 3 so pode comecar quando o estagio 2 acaba.
_e2 = jan[jan["condicao"] == "Choque Termico 5C/40C"].set_index("lote")
_e2_fim = _e2["ini_min"] + pd.to_timedelta(_e2["dias"], unit="D")
_e3_ini = jan[jan["condicao"] != "Choque Termico 5C/40C"].groupby("lote")["ini_min"].min()
_comum = _e3_ini.index.intersection(_e2_fim.index)
assert len(_comum) == 199 and (_e3_ini.loc[_comum] >= _e2_fim.loc[_comum]).all(), (
    "estagios 2 e 3 se sobrepoem: rode o 02_preparar_dados.py corrigido (datas do estagio 3 = inicio + 30 d + tempo)")
rep = np.repeat(np.arange(len(jan)), jan["dias"].to_numpy())
off = np.concatenate([np.arange(n) for n in jan["dias"]])
f_ocup = pd.DataFrame({
    "data": jan["ini_min"].to_numpy()[rep] + pd.to_timedelta(off, unit="D"),
    "lote": jan["lote"].to_numpy()[rep],
    "condicao": jan["condicao"].to_numpy()[rep],
})

# =========================================================================
# 4. Integridade referencial (o que o Power BI faria falhar em silencio)
# =========================================================================
def _fk(fato: pd.DataFrame, col: str, dim: pd.DataFrame, chave: str, nome: str) -> None:
    orf = set(fato[col]) - set(dim[chave])
    assert not orf, f"{nome}: {col} orfao {sorted(orf)[:5]}"

_fk(f_med, "lote", d_lote, "lote", "fMedicoes")
_fk(f_med, "condicao", d_condicao, "condicao", "fMedicoes")
_fk(f_med, "ensaio", d_ensaio, "ensaio", "fMedicoes")
_fk(f_med, "analista", d_analista, "analista", "fMedicoes")
_fk(f_med, "instrumento_ph", d_instrumento, "instrumento_ph", "fMedicoes")
_fk(f_ocup, "lote", d_lote, "lote", "fOcupacaoCamara")
_fk(f_ocup, "condicao", d_condicao, "condicao", "fOcupacaoCamara")
_fk(p_lote_causa, "lote", d_lote, "lote", "pLoteCausa")
_fk(p_lote_causa, "causa", d_causa, "causa", "pLoteCausa")

# =========================================================================
# 5. Escrita (UTF-8, ISO para datas, true/false para booleanos)
# =========================================================================
def _salvar(df: pd.DataFrame, nome: str) -> None:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
        elif out[c].dtype == bool:
            out[c] = out[c].map({True: "true", False: "false"})
    out.to_csv(MODEL_DIR / f"{nome}.csv", index=False, encoding="utf-8")
    print(f"{nome:18s} {len(out):>7,d} linhas x {out.shape[1]:>2d} colunas")

for nome, df in [
    ("dLote", d_lote), ("dCondicao", d_condicao), ("dEnsaio", d_ensaio),
    ("dAnalista", d_analista), ("dInstrumento", d_instrumento), ("dCausa", d_causa),
    ("fMedicoes", f_med), ("fOcupacaoCamara", f_ocup), ("pLoteCausa", p_lote_causa),
]:
    _salvar(df, nome)

# =========================================================================
# 6. Valores de referencia (pandas, independentes do DAX)
# =========================================================================
ref: list[dict] = []

def R(medida: str, contexto: str, valor: float, formato: str = "inteiro") -> None:
    ref.append({"medida": medida, "contexto": contexto, "valor_esperado": valor, "formato": formato})

n_ini = len(d_lote)
n_e1 = int((d_lote["status_estagio1"] == "Aprovado").sum())
n_e3 = int(d_lote["chegou_ao_estagio3"].sum())
n_sob = int(d_lote["sobreviveu_90d"].sum())
# asserts contra os numeros publicados no README do projeto
assert (n_ini, n_e1, n_e3, n_sob) == (300, 241, 199, 127), (n_ini, n_e1, n_e3, n_sob)
assert round(100 * n_sob / n_ini, 1) == 42.3 and round(100 * n_sob / n_e3, 1) == 63.8

R("Lotes iniciados", "sem filtro", n_ini)
R("Lotes aprovados no Estagio 1", "sem filtro", n_e1)
R("Lotes que chegaram ao Estagio 3", "sem filtro", n_e3)
R("Sobreviventes 90d", "sem filtro", n_sob)
R("Taxa cumulativa 90d", "sem filtro", n_sob / n_ini, "percentual")
R("Taxa condicional 90d", "sem filtro", n_sob / n_e3, "percentual")
for k, v in d_lote["estagio_final"].value_counts().items():
    R("Lotes por estagio_final", k, int(v))

for forn, g in d_lote.groupby("fornecedor_tensoativo"):
    R("Lotes iniciados", f"fornecedor={forn}", len(g))
    R("Taxa cumulativa 90d", f"fornecedor={forn}", g["sobreviveu_90d"].mean(), "percentual")
assert round(100 * d_lote.query("fornecedor_tensoativo=='FOR-B'")["sobreviveu_90d"].mean(), 1) == 32.2
assert round(100 * d_lote.query("fornecedor_tensoativo=='FOR-C'")["sobreviveu_90d"].mean(), 1) == 58.8

for fa, g in d_lote.groupby("produto_familia"):
    R("Taxa cumulativa 90d", f"familia={fa}", g["sobreviveu_90d"].mean(), "percentual")
    ch = g["chegou_ao_estagio3"].sum()
    R("Taxa condicional 90d", f"familia={fa}", g.loc[g["chegou_ao_estagio3"], "sobreviveu_90d"].sum() / ch, "percentual")

n_med = len(f_med)
n_jul = int(f_med["julgavel"].sum())
n_oos = int(f_med["oos"].sum())
R("Medicoes realizadas", "sem filtro", n_med)
R("Medicoes julgaveis", "sem filtro", n_jul)
R("Medicoes OOS", "sem filtro", n_oos)
R("% OOS", "sem filtro", n_oos / n_jul, "percentual")
R("Medicoes invalidas (impossiveis)", "sem filtro", int(f_med["valor_impossivel"].sum()))
lotes_oos = f_med.loc[f_med["oos"], "lote"].nunique()
R("Lotes com algum OOS (coluna calculada + contexto de linha)", "sem filtro", lotes_oos)
R("Lotes reprovados", "sem filtro (contraste: OOS de medicao != reprovacao de lote)", len(lotes_reprovados))
for est, g in f_med.merge(d_condicao[["condicao", "estagio"]], on="condicao").groupby("estagio"):
    R("Medicoes OOS", f"estagio={est}", int(g["oos"].sum()))

valido = f_med[~f_med["valor_impossivel"]]
ph = valido[valido["ensaio"] == "ph"].merge(d_lote[["lote", "ph_alvo"]], on="lote")
R("pH medio", "ensaio=ph, sem invalidos", ph["valor"].mean(), "decimal")
R("pH desvio-padrao", "ensaio=ph, sem invalidos", ph["valor"].std(ddof=1), "decimal")
for ins, g in ph.groupby("instrumento_ph"):
    R("Desvio medio do pH vs alvo", f"instrumento={ins}", (g["valor"] - g["ph_alvo"]).mean(), "decimal")
R("Desvio medio do pH vs alvo", "sem filtro", (ph["valor"] - ph["ph_alvo"]).mean(), "decimal")
# pH so tem interpretacao fisica DENTRO de uma familia (alvos de 3,2 a 10,2)
for fa, g in ph.merge(d_lote[["lote", "produto_familia"]], on="lote").groupby("produto_familia"):
    R("pH medio", f"familia={fa}", g["valor"].mean(), "decimal")
    R("pH desvio-padrao", f"familia={fa}", g["valor"].std(ddof=1), "decimal")

dias_cam = len(f_ocup)
desp = int(f_ocup.merge(d_lote[["lote", "sobreviveu_90d"]], on="lote").query("not sobreviveu_90d").shape[0])
assert dias_cam == 241 * 30 + 199 * 4 * 90
R("Dias-camara", "sem filtro", dias_cam)
R("Dias-camara desperdicados", "lotes reprovados", desp)
R("% dias-camara desperdicados", "sem filtro", desp / dias_cam, "percentual")
R("Custo desperdicado (R$) - PREMISSA R$ 50/dia-camara", "parametro=50, ilustrativo", desp * 50, "inteiro")
occ = f_ocup.groupby("data").size()
R("Pico de ocupacao (camaras/dia)", "sem filtro", int(occ.max()))
R("Data do pico de ocupacao", str(occ.idxmax().date()), int(occ.max()))

pd.DataFrame(ref).to_csv(OUT_DIR / "valores_de_referencia.csv", index=False, encoding="utf-8")

# ---- serie mensal para conferir time intelligence e semiaditiva -----------
mes = pd.period_range(
    min(f_med["data_amostra"].min(), f_med["data_inicio_lote"].min()),
    max(f_med["data_amostra"].max(), f_ocup["data"].max()), freq="M",
)
rows = []
for m in mes:
    ini = d_lote[d_lote["data_inicio_teste"].dt.to_period("M") == m]
    oc = occ[occ.index.to_period("M") == m]
    rows.append({
        "ano_mes": str(m),
        "lotes_iniciados_coorte": len(ini),
        "sobreviventes_coorte": int(ini["sobreviveu_90d"].sum()),
        "medicoes_realizadas": int((f_med["data_amostra"].dt.to_period("M") == m).sum()),
        "dias_camara": int(oc.sum()),
        "ocupacao_ultimo_dia_com_dado": int(oc.iloc[-1]) if len(oc) else None,
        "pico_ocupacao": int(oc.max()) if len(oc) else None,
    })
pd.DataFrame(rows).to_csv(OUT_DIR / "referencia_mensal.csv", index=False, encoding="utf-8")
print(f"referencia: {len(ref)} valores + {len(rows)} meses | OK (asserts contra README passaram)")
