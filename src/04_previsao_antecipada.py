"""
04_previsao_antecipada.py: previsao antecipada de falha em estabilidade acelerada
====================================================================================

Pergunta de negocio: cada formulacao que entra na Estabilidade Acelerada ocupa
camara climatica, bancada e analista por 90 dias. Quanto antes eu souber que ela
vai falhar, menos tempo de camara eu desperdico. Este script mede o quanto se
ganha esperando mais informacao, comparando 3 HORIZONTES de decisao:

  H0  dia 0   : so o Teste Inicial (features `d0_*`)
  H1  ~30 d   : H0 + Estabilidade Preliminar (features `e2_*`)
  H2  ~37 d   : H1 + primeira leitura da Acelerada, dia 7 (features `d7_*`)

Alvo: `falha_90d` = lote reprovado em algum ponto da Estabilidade Acelerada
(1 = falha). Restrito aos 199 lotes que CHEGARAM ao Estagio 3: prever o
desfecho de quem nunca entrou no estudo nao e a pergunta, e o proprio funil ja
decidiu isso no Passo 3.

Duas coisas sao medidas e reportadas juntas, nunca uma sem a outra:
  - Divisao TEMPORAL (treina no passado, testa no futuro): a divisao correta
    para uma decisao que sera usada em lotes futuros.
  - Divisao ALEATORIA (mesma proporcao, embaralhada), reproduzida de proposito
    para servir de comparacao. Se a AUC aleatoria for muito maior que a
    temporal, isso e sinal de deriva de distribuicao (a revisao de spec de
    2024-10-01 e a candidata mais provavel), nao de bug.

O limiar de decisao NAO e 0,5: e escolhido para minimizar um CUSTO explicito
(perder uma formulacao que ia falhar custa mais que investigar uma que ia
passar), calibrado no treino e aplicado sem alteracao no teste.

Saidas:
  output/previsao_metricas.json
  output/previsao_importancia_permutacao.csv
  output/figures/03_previsao_antecipada.png
"""

from __future__ import annotations

import json
import os
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             precision_recall_curve, roc_auc_score, roc_curve)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "data"))
OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "output"))
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

SEED = 42
FRACAO_TESTE = 0.22
# Custo de deixar passar uma falha (o lote segue para investigacao/reformulacao
# so depois de ocupar a camara por 90 dias) contra custo de investigar uma
# formulacao boa por engano (revisao extra de bancada, ~1 dia). E uma escolha
# de negocio, nao estatistica; documentada aqui para poder ser discutida e
# trocada, nao para ser tratada como verdade objetiva.
CUSTO_FALSO_NEGATIVO = 4.0
CUSTO_FALSO_POSITIVO = 1.0

resumo: dict = {}

# =========================================================================
# 1. Carga e alvo
# =========================================================================
feat = pd.read_csv(DATA_DIR / "features_por_lote.csv", parse_dates=["data_inicio_teste"])
base = feat[feat.chegou_ao_estagio3].copy().sort_values("data_inicio_teste").reset_index(drop=True)
base["falha_90d"] = (~base.sobreviveu_90d).astype(int)

resumo["populacao"] = dict(
    n_chegaram_estagio3=int(len(base)),
    n_falhas=int(base.falha_90d.sum()),
    taxa_falha_pct=round(100 * base.falha_90d.mean(), 1),
)

# =========================================================================
# 2. Conjuntos de features por horizonte
# =========================================================================
# `analista` e `instrumento_ph` sao DELIBERADAMENTE excluidos das features:
# inclui-los arriscaria o modelo aprender "PH-02 entre set-nov/2024 = risco",
# o vies de instrumento do Passo 2 disfarcado de sinal preditivo, em vez da
# quimica real da formulacao.
CATEGORICAS = ["produto_familia", "fornecedor_tensoativo"]
COLS_D0 = [c for c in base.columns if c.startswith("d0_")]
COLS_E2 = [c for c in base.columns if c.startswith("e2_")]
COLS_D7 = [c for c in base.columns if c.startswith("d7_")]

HORIZONTES = {
    "H0_dia0": COLS_D0,
    "H1_30dias": COLS_D0 + COLS_E2,
    "H2_37dias": COLS_D0 + COLS_E2 + COLS_D7,
}
resumo["horizontes"] = {h: len(v) + len(CATEGORICAS) for h, v in HORIZONTES.items()}

# =========================================================================
# 3. Divisoes: temporal (treina passado, testa futuro) e aleatoria (controle)
# =========================================================================
n_teste = int(round(FRACAO_TESTE * len(base)))
idx_temporal_treino = base.index[:-n_teste]
idx_temporal_teste = base.index[-n_teste:]

idx_aleatorio_treino, idx_aleatorio_teste = train_test_split(
    base.index, test_size=FRACAO_TESTE, random_state=SEED, stratify=base.falha_90d)

resumo["divisao_temporal"] = dict(
    treino_de=str(base.loc[idx_temporal_treino, "data_inicio_teste"].min().date()),
    treino_ate=str(base.loc[idx_temporal_treino, "data_inicio_teste"].max().date()),
    teste_de=str(base.loc[idx_temporal_teste, "data_inicio_teste"].min().date()),
    teste_ate=str(base.loc[idx_temporal_teste, "data_inicio_teste"].max().date()),
    n_treino=int(len(idx_temporal_treino)), n_teste=int(len(idx_temporal_teste)),
    taxa_falha_treino_pct=round(100 * base.loc[idx_temporal_treino, "falha_90d"].mean(), 1),
    taxa_falha_teste_pct=round(100 * base.loc[idx_temporal_teste, "falha_90d"].mean(), 1),
)


def montar_pipeline(modelo, colunas_numericas):
    pre = ColumnTransformer([
        ("num", Pipeline([("imputar", SimpleImputer(strategy="median")),
                          ("escalar", StandardScaler())]), colunas_numericas),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
    ])
    return Pipeline([("preparar", pre), ("modelo", modelo)])


def limiar_por_custo(y_true, proba, custo_fn, custo_fp):
    """Varre limiares candidatos e escolhe o que minimiza custo esperado."""
    candidatos = np.unique(np.clip(proba, 0.001, 0.999))
    melhor_limiar, melhor_custo = 0.5, np.inf
    for lim in candidatos:
        pred = (proba >= lim).astype(int)
        fn = int(((pred == 0) & (y_true == 1)).sum())
        fp = int(((pred == 1) & (y_true == 0)).sum())
        custo = custo_fn * fn + custo_fp * fp
        if custo < melhor_custo:
            melhor_custo, melhor_limiar = custo, lim
    return float(melhor_limiar)


# =========================================================================
# 4. Treinar e avaliar cada horizonte, nas 2 divisoes
# =========================================================================
resultados = []
modelos_treinados = {}   # guarda o pipeline RF de cada horizonte (divisao temporal) p/ figura
y = base.falha_90d.to_numpy()

for nome_h, cols_num in HORIZONTES.items():
    X = base[cols_num + CATEGORICAS]
    for nome_div, (idx_tr, idx_te) in [("temporal", (idx_temporal_treino, idx_temporal_teste)),
                                       ("aleatoria", (idx_aleatorio_treino, idx_aleatorio_teste))]:
        X_tr, X_te = X.loc[idx_tr], X.loc[idx_te]
        y_tr, y_te = y[idx_tr], y[idx_te]

        taxa_maj = max(y_te.mean(), 1 - y_te.mean())

        for nome_m, modelo in [
            ("baseline_classe_majoritaria", DummyClassifier(strategy="most_frequent")),
            ("logistica", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=SEED)),
            ("random_forest", RandomForestClassifier(n_estimators=400, max_depth=6,
                                                      class_weight="balanced", random_state=SEED)),
        ]:
            pipe = montar_pipeline(modelo, cols_num)
            pipe.fit(X_tr, y_tr)
            if hasattr(pipe, "predict_proba"):
                proba_tr = pipe.predict_proba(X_tr)[:, 1]
                proba_te = pipe.predict_proba(X_te)[:, 1]
            else:
                proba_tr = pipe.predict(X_tr).astype(float)
                proba_te = pipe.predict(X_te).astype(float)

            auc = roc_auc_score(y_te, proba_te) if len(set(y_te)) > 1 else np.nan
            pr_auc = average_precision_score(y_te, proba_te) if len(set(y_te)) > 1 else np.nan

            lim = limiar_por_custo(y_tr, proba_tr, CUSTO_FALSO_NEGATIVO, CUSTO_FALSO_POSITIVO)
            pred_te = (proba_te >= lim).astype(int)
            tn, fp, fn, tp = confusion_matrix(y_te, pred_te, labels=[0, 1]).ravel()
            recall_falha = tp / (tp + fn) if (tp + fn) else np.nan
            precisao_falha = tp / (tp + fp) if (tp + fp) else np.nan

            resultados.append(dict(
                horizonte=nome_h, divisao=nome_div, modelo=nome_m,
                n_treino=len(idx_tr), n_teste=len(idx_te),
                auc=round(float(auc), 3) if pd.notna(auc) else None,
                pr_auc=round(float(pr_auc), 3) if pd.notna(pr_auc) else None,
                baseline_classe_majoritaria=round(float(taxa_maj), 3),
                limiar_por_custo=round(lim, 3),
                recall_falha=round(float(recall_falha), 3) if pd.notna(recall_falha) else None,
                precisao_falha=round(float(precisao_falha), 3) if pd.notna(precisao_falha) else None,
                fn=int(fn), fp=int(fp), tp=int(tp), tn=int(tn),
            ))

            if nome_m == "random_forest" and nome_div == "temporal":
                modelos_treinados[nome_h] = dict(pipe=pipe, X_te=X_te, y_te=y_te,
                                                 proba_te=proba_te, limiar=lim)

resultados = pd.DataFrame(resultados)
resumo["resultados"] = resultados.to_dict(orient="records")

# =========================================================================
# 5. Importancia por permutacao (H0, RF, divisao temporal: o modelo que
#    realmente seria usado, decisao no dia 0, validada no futuro)
# =========================================================================
alvo_h0 = modelos_treinados["H0_dia0"]
imp = permutation_importance(alvo_h0["pipe"], alvo_h0["X_te"], alvo_h0["y_te"],
                              n_repeats=30, random_state=SEED, scoring="roc_auc")
importancia = pd.DataFrame({
    "feature": alvo_h0["X_te"].columns,
    "importancia_media": imp.importances_mean,
    "importancia_dp": imp.importances_std,
}).sort_values("importancia_media", ascending=False)
importancia.to_csv(OUT_DIR / "previsao_importancia_permutacao.csv", index=False, encoding="utf-8")

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


fig, ((axa, axb), (axc, axd)) = plt.subplots(2, 2, figsize=(7.6, 6.4))

# (a) AUC vs horizonte, temporal vs aleatoria, so RF
rf = resultados[resultados.modelo == "random_forest"]
x_pos = {"H0_dia0": 0, "H1_30dias": 1, "H2_37dias": 2}
for div, cor, estilo in [("temporal", "#2E6B8A", "-"), ("aleatoria", "#B0B0B0", "--")]:
    sub = rf[rf.divisao == div].assign(x=lambda d: d.horizonte.map(x_pos)).sort_values("x")
    axa.plot(sub.x, sub.auc, marker="o", color=cor, linestyle=estilo, lw=1.6,
            label="Temporal (uso real)" if div == "temporal" else "Aleatória (controle)")
axa.axhline(0.5, color="#C4531A", lw=1.0, linestyle=":")
axa.text(2.02, 0.505, "acaso", fontsize=6.3, color="#C4531A", va="bottom")
axa.set_xticks([0, 1, 2]); axa.set_xticklabels(["Dia 0", "~30 dias", "~37 dias"])
axa.set_ylabel("AUC (RF, lotes de teste)"); axa.set_ylim(0.35, 1.0)
axa.set_title("Dia 0 já captura quase todo o sinal (temporal)", loc="left")
axa.legend(frameon=False, loc="lower right")
panel_letter(axa, "a")

# (b) matriz de confusao: H0, divisao temporal, limiar por custo
h0 = modelos_treinados["H0_dia0"]
pred_h0 = (h0["proba_te"] >= h0["limiar"]).astype(int)
cm = confusion_matrix(h0["y_te"], pred_h0, labels=[0, 1])
im = axb.imshow(cm, cmap="Blues", vmin=0)
for i in range(2):
    for j in range(2):
        cor_txt = "white" if cm[i, j] > cm.max() / 2 else "black"
        axb.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=11, color=cor_txt)
axb.set_xticks([0, 1]); axb.set_xticklabels(["Previu\nsobrevive", "Previu\nfalha"])
axb.set_yticks([0, 1]); axb.set_yticklabels(["Sobreviveu", "Falhou"])
axb.set_ylabel("Real"); axb.set_xlabel("Previsto")
r_h0 = resultados.query("horizonte=='H0_dia0' and divisao=='temporal' and modelo=='random_forest'").iloc[0]
axb.set_title(f"Dia 0 (temporal): recall de falha {r_h0.recall_falha:.0%}, "
             f"limiar {h0['limiar']:.2f}", loc="left")
panel_letter(axb, "b")

# (c) importancia por permutacao, top 10
top = importancia.head(10).iloc[::-1]
NOMES_FEAT = {"d0_ph": "pH (dia 0)", "d0_densidade_g_cm3": "Densidade (dia 0)",
             "d0_delta_e_liberacao": "ΔE liberação", "d0_aspecto_score": "Aspecto",
             "d0_cor_score": "Cor (score)", "d0_odor_conforme": "Odor conforme",
             "d0_estufa50_score": "Estufa 50 °C", "d0_centrifugacao_score": "Centrifugação",
             "d0_agitacao_score": "Agitação magnética", "d0_residuo_ph": "Resíduo de pH vs. alvo",
             "d0_residuo_densidade": "Resíduo de densidade vs. alvo"}
rotulos = [NOMES_FEAT.get(f, f) for f in top.feature]
axc.barh(range(len(top)), top.importancia_media, xerr=top.importancia_dp,
        color="#2E6B8A", height=0.6, error_kw=dict(lw=1.0, ecolor="#7A7A7A"))
axc.set_yticks(range(len(top))); axc.set_yticklabels(rotulos)
axc.set_xlabel("Queda de AUC ao embaralhar a variável")
axc.set_title("O que o modelo do dia 0 realmente usa", loc="left")
panel_letter(axc, "c")

# (d) linha do tempo da divisao temporal
datas = base.data_inicio_teste
axd.scatter(datas.loc[idx_temporal_treino], np.zeros(len(idx_temporal_treino)) + base.loc[idx_temporal_treino, "falha_90d"]*0,
           alpha=0)  # placeholder para eixo de datas
cores_pt = np.where(base.falha_90d.to_numpy() == 1, "#C4531A", "#9CBDCD")
axd.scatter(datas.loc[idx_temporal_treino], [0]*len(idx_temporal_treino),
           c=cores_pt[idx_temporal_treino], s=14, marker="|", linewidths=1.3)
axd.scatter(datas.loc[idx_temporal_teste], [0]*len(idx_temporal_teste),
           c=cores_pt[idx_temporal_teste], s=14, marker="|", linewidths=1.3)
axd.axvline(datas.loc[idx_temporal_teste].min(), color="black", lw=1.1, linestyle="--")
axd.text(datas.loc[idx_temporal_teste].min(), 0.35, " teste →", fontsize=6.8, va="bottom")
axd.set_yticks([])
axd.set_ylim(-0.5, 0.6)
axd.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
axd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
for lbl in axd.get_xticklabels():
    lbl.set_rotation(35); lbl.set_ha("right")
axd.set_xlabel("Data de entrada no Teste Inicial", labelpad=30)
axd.set_title(f"Treino até {resumo['divisao_temporal']['treino_ate']}; "
             f"teste a partir de {resumo['divisao_temporal']['teste_de']}", loc="left")
h_falha = plt.Line2D([0], [0], marker="|", color="#C4531A", linestyle="", ms=9, label="Falhou")
h_ok = plt.Line2D([0], [0], marker="|", color="#9CBDCD", linestyle="", ms=9, label="Sobreviveu")
axd.legend(handles=[h_ok, h_falha], frameon=False, loc="upper left", fontsize=6.5, ncol=2)
panel_letter(axd, "d")

fig.tight_layout(pad=0.7)
fig.savefig(FIG_DIR / "03_previsao_antecipada.png", bbox_inches="tight")

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
with open(OUT_DIR / "previsao_metricas.json", "w", encoding="utf-8") as f:
    json.dump(resumo, f, ensure_ascii=False, indent=2, default=str)

print(f"populacao: {resumo['populacao']}")
print(f"\nsplit temporal: treino {resumo['divisao_temporal']['n_treino']} "
      f"({resumo['divisao_temporal']['treino_de']} a {resumo['divisao_temporal']['treino_ate']}) | "
      f"teste {resumo['divisao_temporal']['n_teste']} "
      f"({resumo['divisao_temporal']['teste_de']} a {resumo['divisao_temporal']['teste_ate']})")
print(f"taxa de falha treino {resumo['divisao_temporal']['taxa_falha_treino_pct']}% "
      f"| teste {resumo['divisao_temporal']['taxa_falha_teste_pct']}%")
print("\n", resultados[["horizonte","divisao","modelo","auc","pr_auc","recall_falha","precisao_falha"]]
      .to_string(index=False))
print("\ntop 5 importancia (H0, RF, temporal):\n", importancia.head(5).to_string(index=False))
