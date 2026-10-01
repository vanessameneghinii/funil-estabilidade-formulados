"""
03_analise_funil.py: atrito, causas e efeito de fornecedor no funil de 3 estagios
====================================================================================

Consome `funil_lotes.csv`, `estagio1_teste_inicial.csv` e `dados_longo.csv`
(saidas do 01 e do 02) e responde tres perguntas de negocio:

  1. Onde o funil perde formulacao, e por qual ensaio?
  2. O fornecedor de tensoativo afeta o resultado, e em qual estagio isso
     aparece pela primeira vez?
  3. Qual familia tem a maior distancia entre "passa a triagem" e "sobrevive
     aos 90 dias", e o que isso diz sobre o mecanismo de falha dela?

Duas taxas de sobrevivencia sao reportadas SEPARADAMENTE, nunca misturadas:
  - CUMULATIVA  = aprovados aos 90 d / total que ENTROU no funil
                  ("de cada 100 formulacoes que comeco, quantas terminam?")
  - CONDICIONAL = aprovados aos 90 d / total que CHEGOU ao Estagio 3
                  ("dado que passou os 2 primeiros criterios de decisao, qual a chance de sobreviver?")

Saidas:
  output/funil_por_familia.csv
  output/funil_por_fornecedor.csv
  output/funil_resumo.json
  output/figures/02_funil_causas_fornecedor.png
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
from scipy.stats import chi2_contingency

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data"))
OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "output"))
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

resumo: dict = {}

# =========================================================================
# 1. Carga
# =========================================================================
# Estes tres arquivos ja passaram pela validacao de schema do 02 (funil_lotes e
# dados_longo sao saida do proprio pipeline); carga simples, sem revalidar.
fun = pd.read_csv(DATA_DIR / "funil_lotes.csv")
e1 = pd.read_csv(DATA_DIR / "estagio1_teste_inicial.csv", parse_dates=["data_inicio_teste"])
dl = pd.read_csv(DATA_DIR / "dados_longo.csv")

assert fun.lote.is_unique, "funil_lotes.csv tem lote duplicado"
N0 = len(fun)
resumo["n_lotes"] = int(N0)

# =========================================================================
# 2. Atrito do funil
# =========================================================================
n_e1 = int((fun.status_estagio1 == "Aprovado").sum())
n_e2 = int((fun.status_estagio2 == "Aprovado").sum())
fun["chegou_e3"] = fun.status_estagio3_90d.notna()
n_e3_entrou = int(fun.chegou_e3.sum())
n_sobrev = int(fun.sobreviveu_90d.sum())

resumo["atrito"] = dict(
    entraram=N0, passaram_e1=n_e1, passaram_e2=n_e2,
    entraram_e3=n_e3_entrou, sobreviveram_90d=n_sobrev,
    taxa_sobrevivencia_cumulativa_pct=round(100 * n_sobrev / N0, 1),
    taxa_sobrevivencia_condicional_pct=round(100 * n_sobrev / n_e3_entrou, 1),
)

# =========================================================================
# 3. Causas por estagio (granular, a partir de dados_longo)
# =========================================================================
# dados_longo tem 1 linha por MEDICAO, com a coluna `oos` ja julgada contra a
# spec vigente (secao 6 do script 02). Contar OOS por (estagio, ensaio) da a
# causa de reprovacao com a mesma granularidade da spec, sem depender do campo
# de texto livre `causa_reprovacao_estagio*` do funil_lotes.
causas = (dl[dl.oos].groupby(["estagio", "ensaio"]).size()
          .rename("n_medicoes_oos").reset_index())
resumo["causas_por_estagio"] = {
    int(est): g.set_index("ensaio").n_medicoes_oos.to_dict()
    for est, g in causas.groupby("estagio")}
causas.to_csv(OUT_DIR / "funil_causas_por_estagio.csv", index=False, encoding="utf-8")

# =========================================================================
# 4. Efeito do fornecedor de tensoativo
# =========================================================================
# Teste em CADA estagio, separadamente: a pergunta e EM QUE ESTAGIO o efeito
# aparece pela primeira vez, nao apenas "existe algum efeito".
tab_e1 = pd.crosstab(e1.fornecedor_tensoativo, e1.status_estagio1)
chi2_e1, p_e1, *_ = chi2_contingency(tab_e1)

tab_90 = pd.crosstab(fun.fornecedor_tensoativo, fun.sobreviveu_90d)
chi2_90, p_90, *_ = chi2_contingency(tab_90)

por_fornecedor = pd.DataFrame({
    "n_lotes": fun.groupby("fornecedor_tensoativo").size(),
    "aprovacao_E1_pct": (e1.groupby("fornecedor_tensoativo").status_estagio1
                        .apply(lambda s: 100 * (s == "Aprovado").mean())),
    "sobrevivencia_90d_cumulativa_pct": (fun.groupby("fornecedor_tensoativo")
                                        .sobreviveu_90d.mean() * 100),
}).round(1)
por_fornecedor.to_csv(OUT_DIR / "funil_por_fornecedor.csv", encoding="utf-8")

resumo["efeito_fornecedor"] = dict(
    tabela=por_fornecedor.to_dict(orient="index"),
    teste_E1=dict(chi2=round(float(chi2_e1), 2), p_valor=round(float(p_e1), 4)),
    teste_sobrevivencia_90d=dict(chi2=round(float(chi2_90), 2), p_valor=round(float(p_90), 4)),
    # Ressalva de metodo: o gerador (01_gerar_dataset.py) atribui a cada lote
    # uma qualidade oculta que carrega um vies por fornecedor, e essa variavel
    # NAO e exposta como feature (ela seria vazamento). O teste abaixo mede o
    # efeito OBSERVADO nos dados disponiveis; nao usa nem tem acesso ao valor
    # oculto. A interpretacao de mecanismo (paragrafo no README) e baseada no
    # desenho do gerador, nao extraida deste teste.
)

# =========================================================================
# 5. Funil por familia: cumulativa vs. condicional, e fotoestabilidade
# =========================================================================
fun["familia_sigla"] = fun.lote.str.split("-").str[0]
por_familia = fun.groupby("familia_sigla").agg(
    n_lotes=("lote", "count"),
    aprovacao_E1_pct=("status_estagio1", lambda s: 100 * (s == "Aprovado").mean()),
    entraram_e3=("chegou_e3", "sum"),
    sobrevivencia_cumulativa_pct=("sobreviveu_90d", lambda s: 100 * s.mean()),
)
sobrev_condicional = (fun[fun.chegou_e3].groupby("familia_sigla")
                      .sobreviveu_90d.mean() * 100)
por_familia["sobrevivencia_condicional_pct"] = sobrev_condicional
foto_nc = (fun[fun.fotoestabilidade_90d.notna()].groupby("familia_sigla")
          .fotoestabilidade_90d.apply(lambda s: (s == "Nao conforme").sum()))
por_familia["fotoestabilidade_nao_conforme_n"] = foto_nc.fillna(0).astype(int)
por_familia = por_familia.round(1).sort_values("sobrevivencia_cumulativa_pct")
por_familia.to_csv(OUT_DIR / "funil_por_familia.csv", encoding="utf-8")
resumo["funil_por_familia"] = por_familia.reset_index().to_dict(orient="records")

# =========================================================================
# 6. Figura de 4 paineis
# =========================================================================
plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 300, "font.size": 8,
    "axes.titlesize": 8.5, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlelocation": "left", "figure.autolayout": False,
})


def panel_letter(ax, letra):
    ax.text(-0.14, 1.04, letra, transform=ax.transAxes, fontsize=11,
            fontweight="bold", va="bottom", ha="left")


fig, ((axa, axb), (axc, axd)) = plt.subplots(2, 2, figsize=(7.6, 6.4))

# (a) atrito do funil
etapas = ["Entram no\nTeste Inicial", "Aprovados no\nTeste Inicial",
          "Aprovados na\nEstab. Preliminar", "Aprovados\naos 90 dias"]
vals = [N0, n_e1, n_e2, n_sobrev]
cores_barra = ["#BFD3DE", "#9CBDCD", "#6FA0B8", "#2E6B8A"]
yy = np.arange(4)[::-1]
axa.barh(yy, vals, color=cores_barra, height=0.62)
for y_, v in zip(yy, vals):
    axa.text(v + 6, y_, f"{v}", va="center", ha="left", fontsize=7)
axa.set_yticks(yy); axa.set_yticklabels(etapas)
axa.set_xlim(0, N0 * 1.22); axa.set_xlabel("Formulações (n)")
axa.set_title(f"{n_sobrev} de {N0} sobrevivem aos 90 dias "
             f"({resumo['atrito']['taxa_sobrevivencia_cumulativa_pct']:.0f}% cumulativo)",
             loc="left")
panel_letter(axa, "a")

# (b) causas por estagio, empilhado
piv_causas = causas.pivot_table(index="ensaio", columns="estagio",
                                values="n_medicoes_oos", fill_value=0)
piv_causas = piv_causas.reindex(columns=[1, 2, 3]).fillna(0)
piv_causas["total"] = piv_causas.sum(axis=1)
piv_causas = piv_causas.sort_values("total").drop(columns="total")
NOMES_ENSAIO = {"agitacao_score": "Agitação magnética", "aspecto_score": "Aspecto",
                "centrifugacao_score": "Centrifugação", "delta_e_liberacao": "Cor (liberação)",
                "densidade_g_cm3": "Densidade", "estufa50_score": "Estufa 50 °C",
                "odor_conforme": "Odor", "ph": "pH"}
cores_estagio = ["#CBDCE6", "#7FA9C0", "#2E6B8A"]
esq = np.zeros(len(piv_causas))
yb = np.arange(len(piv_causas))
for cor, est in zip(cores_estagio, [1, 2, 3]):
    axb.barh(yb, piv_causas[est].to_numpy(), left=esq, color=cor, height=0.66,
            label=f"Estágio {est}")
    esq += piv_causas[est].to_numpy()
axb.set_yticks(yb); axb.set_yticklabels([NOMES_ENSAIO[e] for e in piv_causas.index])
axb.set_xlabel("Medições fora de especificação (n)")
axb.set_title("Cada estágio reprova por um ensaio diferente", loc="left")
axb.legend(frameon=False, loc="lower right", fontsize=6.5)
panel_letter(axb, "b")

# (c) fornecedor: aprovacao E1 (sem efeito) vs sobrevivencia 90d (com efeito)
x = np.arange(3)
w = 0.36
axc.bar(x - w/2, por_fornecedor.aprovacao_E1_pct, width=w, color="#9CBDCD",
       label="Aprovação no Teste Inicial")
axc.bar(x + w/2, por_fornecedor.sobrevivencia_90d_cumulativa_pct, width=w,
       color="#2E6B8A", label="Sobrevivência aos 90 dias")
axc.set_xticks(x); axc.set_xticklabels(por_fornecedor.index)
axc.set_ylabel("% dos lotes"); axc.set_ylim(0, 100)
p_txt_90 = "p < 0,001" if p_90 < 0.001 else f"p = {p_90:.3f}"
p_txt_e1 = "sem separar" if p_e1 >= 0.05 else "já separa fracamente"
axc.set_title(f"Fornecedor {p_txt_e1} no dia 0 (p = {p_e1:.3f}),\nmais forte aos 90 d ({p_txt_90})",
             loc="left")
axc.legend(frameon=False, loc="upper right", fontsize=6.3)
panel_letter(axc, "c")

# (d) por familia: cumulativa vs condicional
familias_ord = por_familia.index.tolist()
yf = np.arange(len(familias_ord))
axd.hlines(yf, por_familia.sobrevivencia_cumulativa_pct, por_familia.sobrevivencia_condicional_pct,
          color="#B0B0B0", lw=1.6, zorder=1)
axd.scatter(por_familia.sobrevivencia_cumulativa_pct, yf, color="#2E6B8A", s=32,
           zorder=2, label="Cumulativa (de todos os que entraram)")
axd.scatter(por_familia.sobrevivencia_condicional_pct, yf, color="#C4531A", s=32,
           marker="D", zorder=2, label="Condicional (dado que chegou ao E3)")
axd.set_yticks(yf); axd.set_yticklabels(familias_ord)
axd.set_xlabel("% sobrevivência aos 90 dias"); axd.set_xlim(0, 128)
axd.set_xticks([0, 20, 40, 60, 80, 100])
axd.set_title("A distância entre as duas é o custo dos 2 primeiros critérios de decisão", loc="left")
axd.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.0, -0.2), fontsize=6.3)
panel_letter(axd, "d")

fig.tight_layout(pad=0.7)
fig.savefig(FIG_DIR / "02_funil_causas_fornecedor.png", bbox_inches="tight")

r = fig.canvas.get_renderer()
textos = [(t, t.get_window_extent(r)) for t in fig.findobj(matplotlib.text.Text)
         if t.get_text().strip() and t.get_visible()]
sobrepostos = [(a.get_text()[:20], b.get_text()[:20]) for i, (a, ba) in enumerate(textos)
              for b, bb in textos[i+1:] if ba.overlaps(bb)]
if sobrepostos:
    print("ATENCAO: textos sobrepostos:", sobrepostos)
plt.close(fig)

# =========================================================================
# 7. Gravacao
# =========================================================================
with open(OUT_DIR / "funil_resumo.json", "w", encoding="utf-8") as f:
    json.dump(resumo, f, ensure_ascii=False, indent=2, default=str)

print(f"atrito: {N0} -> {n_e1} -> {n_e2} -> {n_sobrev} "
      f"({resumo['atrito']['taxa_sobrevivencia_cumulativa_pct']}% cumulativo, "
      f"{resumo['atrito']['taxa_sobrevivencia_condicional_pct']}% condicional)")
print(f"fornecedor: E1 p={p_e1:.4f} (sem efeito) | 90d p={p_90:.4f} "
      f"({'COM efeito' if p_90 < 0.05 else 'sem efeito'})")
print(por_fornecedor.to_string())
print("\npor familia:\n", por_familia.to_string())
