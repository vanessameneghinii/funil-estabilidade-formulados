"""
05_clusterizacao.py: agrupamento por assinatura de degradacao
====================================================================================

Pergunta de negocio (ICH Q1D, bracketing e matrixing): produtos que degradam
DA MESMA FORMA podem compartilhar protocolo de estabilidade, independente do
nome comercial da familia. Este script descobre esses grupos sem usar o rotulo
de familia, e depois testa se o agrupamento encontrado coincide com a familia
declarada ou junta familias diferentes, o que e o resultado interessante em
qualquer um dos dois casos.

Metodo:
  1. Para cada lote que chegou ao Estagio 3 (199), ajustar a INCLINACAO
     (regressao linear simples no tempo) de pH, delta_b* (amarelecimento) e
     delta_L* (escurecimento) em cada uma das 4 condicoes de armazenamento.
     Isso da um vetor de 12 numeros por lote: a "assinatura" de como ele
     degrada, independente do nivel inicial (so a inclinacao da deriva).
  2. Padronizar (z-score) e agrupar com K-means; o numero de grupos e
     escolhido pelo pico da silhueta media, testando k=2..8.
  3. Comparar contra a hierarquica (Ward) sobre o mesmo vetor, como checagem
     de robustez: dois metodos diferentes devem concordar em estrutura, nao
     necessariamente em rotulo.
  4. Medir concordancia com a familia DECLARADA via Adjusted Rand Index (ARI):
     ARI alto = os grupos descobertos sao so as familias; ARI baixo = os
     grupos nao seguem as familias. A tabela cluster x familia mostra se eles
     juntam familias diferentes (o resultado que sustenta o bracketing: dois
     produtos de familias diferentes que degradam igual) ou dividem uma familia.

Saidas:
  output/clusterizacao_resultado.csv   (lote, familia, cluster)
  output/perfil_clusters.csv           (centroide de cada cluster)
  output/figures/04_clusterizacao.png
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
from scipy.cluster.hierarchy import dendrogram, linkage
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data"))
OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "output"))
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
SEED = 42

resumo: dict = {}

# =========================================================================
# 1. Carga e vetor de inclinacao por lote
# =========================================================================
e3 = pd.read_csv(DATA_DIR / "estagio3_estabilidade_acelerada.csv")
CONDICOES = ["Geladeira 5C", "Ambiente Escuro 25C", "Estufa 40C", "Luz Solar"]
NOMES_COND = {"Geladeira 5C": "Geladeira", "Ambiente Escuro 25C": "Ambiente",
             "Estufa 40C": "Estufa", "Luz Solar": "Luz"}


def inclinacao(grupo: pd.DataFrame, coluna: str) -> float:
    """Inclinacao (por dia) de uma regressao linear simples no tempo."""
    if grupo[coluna].notna().sum() < 3:
        return np.nan
    coef = np.polyfit(grupo.tempo_dias, grupo[coluna], 1)
    return coef[0]


linhas = []
for lote, g in e3.groupby("lote"):
    linha = {"lote": lote, "produto_familia": g.produto_familia.iloc[0]}
    for cond in CONDICOES:
        gc = g[g.condicao == cond].sort_values("tempo_dias")
        linha[f"incl_ph_{NOMES_COND[cond]}"] = inclinacao(gc, "ph")
        linha[f"incl_amarelecimento_{NOMES_COND[cond]}"] = inclinacao(gc, "delta_b")
        linha[f"incl_escurecimento_{NOMES_COND[cond]}"] = -inclinacao(gc, "delta_L")
    linhas.append(linha)
vetores = pd.DataFrame(linhas)

COLS_INCLINACAO = [c for c in vetores.columns if c.startswith("incl_")]
resumo["n_lotes"] = int(len(vetores))
resumo["dimensoes_vetor"] = len(COLS_INCLINACAO)
resumo["lotes_com_valor_faltante"] = int(vetores[COLS_INCLINACAO].isna().any(axis=1).sum())

X = vetores[COLS_INCLINACAO].fillna(vetores[COLS_INCLINACAO].median())
Xz = StandardScaler().fit_transform(X)

# =========================================================================
# 2. Escolher k pela silhueta
# =========================================================================
silhuetas = {}
for k in range(2, 9):
    km = KMeans(n_clusters=k, random_state=SEED, n_init=10).fit(Xz)
    silhuetas[k] = silhouette_score(Xz, km.labels_)
k_escolhido = max(silhuetas, key=silhuetas.get)
resumo["silhueta_por_k"] = {k: round(v, 3) for k, v in silhuetas.items()}
resumo["k_escolhido"] = k_escolhido

kmeans = KMeans(n_clusters=k_escolhido, random_state=SEED, n_init=10).fit(Xz)
vetores["cluster"] = kmeans.labels_
resumo["silhueta_kmeans"] = round(silhouette_score(Xz, kmeans.labels_), 3)
resumo["tamanho_clusters"] = vetores.cluster.value_counts().sort_index().to_dict()

# =========================================================================
# 3. Robustez: hierarquica (Ward) com o mesmo k, e ARI entre os dois metodos
# =========================================================================
ligacao = linkage(Xz, method="ward")
from scipy.cluster.hierarchy import fcluster
labels_ward = fcluster(ligacao, t=k_escolhido, criterion="maxclust") - 1
ari_metodos = adjusted_rand_score(kmeans.labels_, labels_ward)
resumo["ari_kmeans_vs_ward"] = round(float(ari_metodos), 3)

# =========================================================================
# 4. O cluster descoberto coincide com a familia DECLARADA, ou junta familias diferentes?
# =========================================================================
ari_familia = adjusted_rand_score(vetores.produto_familia, kmeans.labels_)
resumo["ari_cluster_vs_familia_declarada"] = round(float(ari_familia), 3)
tab_familia = pd.crosstab(vetores.cluster, vetores.produto_familia)
resumo["cluster_x_familia"] = tab_familia.to_dict()

# =========================================================================
# 5. Perfil de cada cluster (centroide em unidades originais, mais interpretavel)
# =========================================================================
perfil = vetores.groupby("cluster")[COLS_INCLINACAO].mean().round(5)
perfil.insert(0, "n_lotes", vetores.cluster.value_counts().sort_index())
perfil.to_csv(OUT_DIR / "perfil_clusters.csv", encoding="utf-8")
resumo["perfil_clusters"] = perfil.reset_index().to_dict(orient="records")

vetores[["lote", "produto_familia", "cluster"] + COLS_INCLINACAO].to_csv(
    OUT_DIR / "clusterizacao_resultado.csv", index=False, encoding="utf-8")

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
    ax.text(-0.16, 1.05, letra, transform=ax.transAxes, fontsize=11,
            fontweight="bold", va="bottom", ha="left")


PALETA_CLUSTER = ["#2E6B8A", "#C4531A", "#5B8C5A", "#8C6BAF", "#B0A020"][:k_escolhido]

fig, ((axa, axb), (axc, axd)) = plt.subplots(2, 2, figsize=(7.8, 6.6))

# (a) silhueta vs k
ks = sorted(silhuetas)
axa.plot(ks, [silhuetas[k] for k in ks], marker="o", color="#2E6B8A", lw=1.6)
axa.scatter([k_escolhido], [silhuetas[k_escolhido]], color="#C4531A", s=60, zorder=3)
axa.annotate(f"k={k_escolhido} escolhido", (k_escolhido, silhuetas[k_escolhido]),
            xytext=(9, 9), textcoords="offset points", fontsize=6.8, color="#C4531A")
axa.set_ylim(0, max(silhuetas.values()) * 1.3)  # folga no topo: evita que o tick mais alto encoste na letra do painel
axa.set_xlabel("Número de clusters (k)"); axa.set_ylabel("Silhueta média")
axa.set_title("k escolhido pelo pico da silhueta", loc="left")
panel_letter(axa, "a")

# (b) PCA 2D colorido por cluster
pca = PCA(n_components=2, random_state=SEED)
coords = pca.fit_transform(Xz)
var_exp = pca.explained_variance_ratio_
for c in range(k_escolhido):
    m = vetores.cluster == c
    axb.scatter(coords[m, 0], coords[m, 1], s=18, color=PALETA_CLUSTER[c],
               label=f"Cluster {c} (n={m.sum()})", alpha=0.85)
axb.set_xlabel(f"CP1 ({var_exp[0]:.0%} da variância)")
axb.set_ylabel(f"CP2 ({var_exp[1]:.0%} da variância)")
axb.set_title("Separação dos clusters no espaço de inclinações", loc="left")
axb.legend(frameon=False, loc="best", fontsize=6.3)
panel_letter(axb, "b")

# (c) heatmap dos centroides
centroide_z = pd.DataFrame(Xz, columns=COLS_INCLINACAO).groupby(vetores.cluster.to_numpy()).mean()
NOMES_LINHA = {"ph": "pH", "amarelecimento": "b* (amarelo)", "escurecimento": "L* (escuro)"}
rotulos_curtos = []
for c in COLS_INCLINACAO:
    _, tipo, cond = c.split("_", 2)
    rotulos_curtos.append(f"{NOMES_LINHA[tipo]} · {cond}")
im = axc.imshow(centroide_z.T, cmap="RdBu_r", vmin=-2, vmax=2, aspect="auto")
axc.set_xticks(range(k_escolhido)); axc.set_xticklabels([f"C{c}" for c in range(k_escolhido)])
axc.set_yticks(range(len(COLS_INCLINACAO))); axc.set_yticklabels(rotulos_curtos, fontsize=6.4)
for i in range(len(COLS_INCLINACAO)):
    for j in range(k_escolhido):
        axc.text(j, i, f"{centroide_z.T.iloc[i, j]:.1f}", ha="center", va="center", fontsize=5.8)
cbar = fig.colorbar(im, ax=axc, fraction=0.05, pad=0.04)
cbar.set_label("z-score do centroide", fontsize=6.5)
axc.set_title("Assinatura de cada cluster (padronizada)", loc="left")
panel_letter(axc, "c")

# (d) cluster x familia declarada: mostra se o cluster junta familias ou divide uma
tab_pct = tab_familia.div(tab_familia.sum(axis=1), axis=0) * 100
esq = np.zeros(k_escolhido)
cores_fam = plt.cm.tab10(np.linspace(0, 1, tab_familia.shape[1]))
for i, fam in enumerate(tab_familia.columns):
    axd.barh(range(k_escolhido), tab_pct[fam], left=esq, color=cores_fam[i],
            height=0.6, label=fam.split(" ")[0])
    esq += tab_pct[fam].to_numpy()
axd.set_yticks(range(k_escolhido)); axd.set_yticklabels([f"Cluster {c}" for c in range(k_escolhido)])
axd.set_xlabel("% dos lotes do cluster, por família declarada")
familias_divididas = int((tab_familia.gt(0).sum(axis=0) > 1).sum())  # familias presentes em >1 cluster
if ari_familia > 0.4:
    txt_famil = "clusters ≈ famílias"
elif familias_divididas == 0:
    txt_famil = "nenhuma família é dividida"
else:
    txt_famil = f"{familias_divididas} família(s) dividida(s)"
axd.set_title(f"ARI cluster×família = {ari_familia:.2f} ({txt_famil})", loc="left")
axd.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=3, fontsize=6.0)
panel_letter(axd, "d")

fig.tight_layout(pad=0.8)
fig.savefig(FIG_DIR / "04_clusterizacao.png", bbox_inches="tight")

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
with open(OUT_DIR / "clusterizacao_resumo.json", "w", encoding="utf-8") as f:
    json.dump(resumo, f, ensure_ascii=False, indent=2, default=str)

print(f"lotes: {resumo['n_lotes']} | vetor de {resumo['dimensoes_vetor']} dimensoes | "
      f"faltantes: {resumo['lotes_com_valor_faltante']}")
print(f"k escolhido: {k_escolhido} | silhueta: {resumo['silhueta_kmeans']}")
print(f"ARI k-means vs. Ward: {resumo['ari_kmeans_vs_ward']}")
print(f"ARI cluster vs. familia declarada: {ari_familia:.3f}")
print("\ntamanho dos clusters:", resumo["tamanho_clusters"])
print("\ncluster x familia (contagem):\n", tab_familia.to_string())
print("\nperfil (centroide em graus/dE por dia):\n", perfil.to_string())
