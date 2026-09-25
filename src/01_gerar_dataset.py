"""
Gerador de dataset sintetico — controle de qualidade e estudo de estabilidade
de saneantes (produtos de limpeza) formulados.

Estrutura: funil de tres estagios com portoes de aprovacao, espelhando a pratica
de laboratorio de desenvolvimento:

  Estagio 1 — Teste Inicial (dia 0)
      organolepticas + pH + densidade + estufa 50 C 48 h + centrifugacao
      3000 rpm/30 min + agitacao magnetica.  Portao: reprova em qualquer
      ensaio encerra a formulacao.

  Estagio 2 — Estabilidade Preliminar (choque termico)
      geladeira 5 C <-> estufa 40 C em dias alternados; avaliacoes em 15 e 30 d.
      Portao no dia 30.

  Estagio 3 — Estabilidade Acelerada
      4 condicoes (ambiente escuro 25 C, estufa 40 C, geladeira 5 C, luz solar);
      avaliacoes em 7, 15, 30, 60 e 90 d.

Decisoes de modelagem (justificadas no relatorio tecnico):
  - pH em valor absoluto (escala logaritmica), densidade em valor absoluto,
    ambos com distribuicao normal em torno do alvo da familia.
  - Cor gerada em CIE L*a*b*: sorteia-se L*, a*, b* da amostra em torno do
    padrao da familia e o Delta-E e CALCULADO por CIEDE2000 (ASTM D2244
    recomenda dE00 para diferencas de 0 a 5 unidades).  Assim o Delta-E
    e nao-negativo e assimetrico por construcao, e os componentes
    dL*/da*/db* ficam disponiveis para diagnostico de causa.
  - Deriva por mecanismo: componente de Arrhenius (Ea = 80 kJ/mol) atuando em
    pH e densidade, e componente dependente de DOSE de radiacao atuando em
    b* (amarelecimento) e L* apenas na condicao de luz.  Estufa e luz sao
    mecanismos distintos, nao o mesmo ruido reescalado.
  - Qualidade latente do lote (robustez da emulsao) governa simultaneamente os
    escores de estresse do Estagio 1 e as taxas de deriva do Estagio 3.  E isso
    que torna a previsao antecipada possivel sem vazamento: os ensaios de
    bancada do dia 0 sao observacoes ruidosas da mesma variavel latente que
    determina o desfecho aos 90 dias.
  - Avaliacao organoleptica gerada em DUAS camadas: texto livre do analista
    (como a planilha real registra) e escore ordinal 0-4 derivado dele.
  - Erros reais de laboratorio injetados com gabarito separado: decimal
    deslocado, replicata trocada, sonda descalibrada (vies por instrumento e
    janela de datas) e lote de insumo enviesado por fornecedor.

Escopo: saneantes convencionais. Nenhum sistema nano ou microencapsulado;
fragrancia livre (nao encapsulada) em todas as familias.

Reprodutibilidade: seed fixo em SEED. Rodar este script do zero reproduz
integralmente a pasta de saida.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_LOTES = 300
OUT_DIR = Path(os.environ.get("OUT_DIR", "data"))

rng = np.random.default_rng(SEED)

# --------------------------------------------------------------------------
# 1. Familias de produto, alvos e limites de especificacao
# --------------------------------------------------------------------------
# pH: faixas coerentes com a quimica de cada sistema (anionico proximo do
# neutro, multiuso alcalino, amaciante catonico acido, alvejante de oxigenio
# estabilizado em meio acido).
# Padrao de cor em L*a*b* (D65/10 graus) por familia.

FAMILIAS = {
    # Faixas de pH: ver FONTES.md. [LIT] = faixa de literatura/regulacao;
    # [EST] = estimativa de engenharia com justificativa quimica.
    # Restricao regulatoria transversal (ANVISA RDC 59/2010 art. 3; RDC 184/2001):
    # saneante de Risco 1 tem pH na forma pura > 2 e < 11,5 e nao possui atividade
    # antimicrobiana. Produto com acao desinfetante e Risco 2 (registro).
    "Detergente Liquido Lava-Loucas": dict(
        sigla="DLL", anvisa="Risco 1", fonte_ph="[LIT] formulacoes de lava-loucas: pH 6,8 a 9,0",
        ph_alvo=7.60, ph_min=6.80, ph_max=8.60, ph_sd=0.20,
        dens_alvo=1.032, dens_min=1.020, dens_max=1.045, dens_sd=0.0048,
        lab_padrao=(88.0, -4.5, 28.0),
        k_ph=0.0008, k_dens=0.000014, k_cor=0.0060, foto=1.00,
        agitacao_aplicavel=True, excecao_centrifugacao=None),
    "Detergente Liquido para Roupas": dict(
        sigla="DLR", anvisa="Risco 1", fonte_ph="[LIT] produtos de lavanderia: pH 9 a 11; formulacao-modelo de fornecedor: pH 10,5 e densidade 1,02",
        ph_alvo=9.60, ph_min=8.50, ph_max=10.50, ph_sd=0.24,
        dens_alvo=1.022, dens_min=1.010, dens_max=1.035, dens_sd=0.0045,
        lab_padrao=(82.0, 12.0, 6.0),
        k_ph=0.0009, k_dens=0.000012, k_cor=0.0065, foto=1.10,
        agitacao_aplicavel=True, excecao_centrifugacao=None),
    "Limpador Multiuso Alcalino": dict(
        sigla="LMU", anvisa="Risco 1", fonte_ph="[LIT+EST] teto de 11,0 como margem do corte regulatorio de 11,5 (Risco 1)",
        ph_alvo=10.20, ph_min=9.50, ph_max=11.00, ph_sd=0.22,
        dens_alvo=1.010, dens_min=1.000, dens_max=1.025, dens_sd=0.0042,
        lab_padrao=(72.0, -22.0, 12.0),
        k_ph=0.0012, k_dens=0.000012, k_cor=0.0075, foto=1.25,
        agitacao_aplicavel=True, excecao_centrifugacao=None),
    "Desinfetante Quaternario Concentrado": dict(
        sigla="DES", anvisa="Risco 2", fonte_ph="[EST] quaternario formulado proximo da neutralidade; Risco 2 por atividade antimicrobiana",
        ph_alvo=7.00, ph_min=6.00, ph_max=8.00, ph_sd=0.20,
        dens_alvo=1.005, dens_min=0.995, dens_max=1.020, dens_sd=0.0040,
        lab_padrao=(65.0, -8.0, -28.0),
        k_ph=0.0007, k_dens=0.000010, k_cor=0.0055, foto=1.40,
        agitacao_aplicavel=False, excecao_centrifugacao=None),
    "Amaciante de Roupas (esterquat)": dict(
        sigla="AMA", anvisa="Risco 1", fonte_ph="[LIT] esterquat exige pH 2,0 a 5,0, preferencialmente 2,5 a 4,0, para estabilidade hidrolitica do ester",
        ph_alvo=3.20, ph_min=2.50, ph_max=4.00, ph_sd=0.20,
        dens_alvo=0.996, dens_min=0.985, dens_max=1.010, dens_sd=0.0042,
        lab_padrao=(90.0, 3.0, -6.0),
        # hidrolise do ester e o mecanismo dominante: maior taxa de deriva de pH
        k_ph=0.0013, k_dens=0.000016, k_cor=0.0070, foto=0.85,
        agitacao_aplicavel=True,
        excecao_centrifugacao=(
            "Sistema catonico: leve cremeacao reversivel a agitacao e esperada "
            "na centrifugacao; aceitar escore <= 3.")),
    "Alvejante Liquido sem Cloro": dict(
        sigla="ALV", anvisa="Risco 1", fonte_ph="[EST] peroxido de hidrogenio se decompoe por catalise basica; alvejantes liquidos de oxigenio sao estabilizados em meio acido",
        ph_alvo=4.20, ph_min=3.50, ph_max=5.00, ph_sd=0.18,
        dens_alvo=1.045, dens_min=1.030, dens_max=1.060, dens_sd=0.0048,
        lab_padrao=(94.0, -1.0, 4.0),
        k_ph=0.0014, k_dens=0.000018, k_cor=0.0050, foto=1.55,
        agitacao_aplicavel=True,
        excecao_centrifugacao=(
            "Estabilizante insoluvel: precipitado fino no fundo apos "
            "centrifugacao e considerado normal; aceitar escore <= 3.")),
}

FORNECEDORES = {"FOR-A": 0.00, "FOR-B": -0.55, "FOR-C": 0.10}  # efeito na robustez

# Limites organolepticos comuns a todas as familias
LIM_ASPECTO = 2          # escore <= 2 conforme (2 = limitrofe)
LIM_ESTRESSE = 2         # estufa 50 C / centrifugacao / agitacao
# Tolerancia de cor na liberacao: a spec foi REVISADA dentro do periodo coberto
# pelo dataset. Julgar cada lote contra a spec vigente NA DATA DA AMOSTRA e o
# ponto do exercicio de juncao por vigencia (script 02).
LIM_DELTA_E_LIB_V10 = 2.00        # dE00 de liberacao, v1.0: 2024-01-01 a 2024-09-30
LIM_DELTA_E_LIB_V11 = 1.50        # dE00 de liberacao, v1.1: a partir de 2024-10-01
DATA_REVISAO_SPEC = pd.Timestamp("2024-10-01")
LIM_CENTRIFUGA_EXCECAO = 3        # familias com excecao declarada na spec
LIM_DELTA_E_EST = 3.00   # dE00 de estabilidade (Tx vs T0 do proprio lote)
LIM_DELTA_E_FOTO = 6.00  # dE00 sob luz solar — endpoint de fotoestabilidade

CONDICOES = {
    # nome: (temperatura K, taxa de dose relativa de luz)
    "Ambiente Escuro 25C": (298.15, 0.0),
    "Estufa 40C": (313.15, 0.0),
    "Geladeira 5C": (278.15, 0.0),
    "Luz Solar": (303.15, 1.0),
}
TEMPOS_E3 = [7, 15, 30, 60, 90]
TEMPOS_E2 = [15, 30]

EA = 80_000.0     # J/mol — faixa tipica de degradacao em formulados
R_GAS = 8.314
T_REF = 298.15


def fator_arrhenius(T: float) -> float:
    """Aceleracao da taxa de degradacao em T relativa a 25 C."""
    return float(np.exp(EA / R_GAS * (1.0 / T_REF - 1.0 / T)))


# --------------------------------------------------------------------------
# 2. Diferenca de cor CIEDE2000 (ISO/CIE 11664-6; ASTM D2244)
# --------------------------------------------------------------------------
def delta_e_2000(lab1, lab2) -> float:
    """dE00 entre padrao (lab1) e amostra (lab2). kL = kC = kH = 1."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = 0.5 * (C1 + C2)
    Cbar7 = Cbar ** 7
    G = 0.5 * (1.0 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))

    a1p, a2p = (1.0 + G) * a1, (1.0 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)

    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0.0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180.0:
        dhp = h2p - h1p
    elif h2p - h1p > 180.0:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0
    dHp = 2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)

    Lbarp = 0.5 * (L1 + L2)
    Cbarp = 0.5 * (C1p + C2p)

    if C1p * C2p == 0.0:
        hbarp = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hbarp = 0.5 * (h1p + h2p)
    elif (h1p + h2p) < 360.0:
        hbarp = 0.5 * (h1p + h2p + 360.0)
    else:
        hbarp = 0.5 * (h1p + h2p - 360.0)

    T = (1.0
         - 0.17 * np.cos(np.radians(hbarp - 30.0))
         + 0.24 * np.cos(np.radians(2.0 * hbarp))
         + 0.32 * np.cos(np.radians(3.0 * hbarp + 6.0))
         - 0.20 * np.cos(np.radians(4.0 * hbarp - 63.0)))

    dTheta = 30.0 * np.exp(-(((hbarp - 275.0) / 25.0) ** 2))
    Cbarp7 = Cbarp ** 7
    Rc = 2.0 * np.sqrt(Cbarp7 / (Cbarp7 + 25.0 ** 7))
    SL = 1.0 + (0.015 * (Lbarp - 50.0) ** 2) / np.sqrt(20.0 + (Lbarp - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cbarp
    SH = 1.0 + 0.015 * Cbarp * T
    RT = -np.sin(np.radians(2.0 * dTheta)) * Rc

    return float(np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                         + RT * (dCp / SC) * (dHp / SH)))


# --------------------------------------------------------------------------
# 3. Vocabulario de laboratorio: escore ordinal -> texto livre do analista
# --------------------------------------------------------------------------
TXT_ASPECTO = {
    0: ["liquido homogeneo, limpido", "liquido homogeneo, levemente opalescente",
        "liquido homogeneo, sem alteracao"],
    1: ["liquido homogeneo com leve pelicula na superficie",
        "homogeneo, leve turvacao em relacao ao padrao"],
    2: ["cremeacao visivel na superficie, reversivel a agitacao",
        "leve cremeacao na superficie, porem conforme"],
    3: ["separacao parcial de fase, camada superior definida",
        "sedimento no fundo nao reincorporavel"],
    4: ["separacao franca de fases; coalescencia evidente",
        "quebra de emulsao com sobrenadante limpido"],
}
TXT_ESTUFA = {
    0: ["sem alteracao apos 48 h a 50 C"],
    1: ["leve pelicula na superficie apos 48 h, conforme"],
    2: ["cremeacao na superficie de cor mais alaranjada, porem conforme",
        "leve cremeacao na superficie, reversivel"],
    3: ["separacao parcial apos 48 h a 50 C"],
    4: ["separacao franca apos 48 h; produto inviavel"],
}
TXT_CENTRIFUGA = {
    0: ["sem separacao apos 3000 rpm / 30 min"],
    1: ["leve pelicula na superficie apos centrifugacao"],
    2: ["precipitado fino no fundo apos centrifugacao",
        "leve cremeacao reversivel apos centrifugacao"],
    3: ["separacao parcial apos centrifugacao"],
    4: ["separacao franca com sobrenadante limpido apos centrifugacao"],
}
TXT_AGITACAO = {
    0: ["homogeneiza em menos de 2 min, sem alteracao"],
    1: ["homogeneiza em cerca de 5 min"],
    2: ["homogeneiza com dificuldade, aspecto final conforme"],
    3: ["nao reincorpora totalmente apos 10 min"],
    4: ["nao reincorpora; fases permanecem separadas"],
}
TXT_ODOR = {True: ["caracteristico", "caracteristico do produto"],
            False: ["alterado, notas rancosas", "caracteristico, porem alterado"]}
TXT_COR = {
    0: ["conforme padrao"],
    1: ["levemente diferente do padrao, conforme"],
    2: ["perceptivelmente mais escura que o padrao"],
    3: ["amarelada em relacao ao padrao"],
    4: ["desbotada em relacao ao padrao"],
}


def escore_para_texto(tabela, escore, gen):
    return str(gen.choice(tabela[int(escore)]))


def escore_ordinal(latente, gen, limiares=(-0.35, 0.75, 1.65, 2.35)):
    """Converte um estresse latente continuo em escore ordinal 0-4.

    Limiares fixos (nao sorteados) para que o escore seja monotonico no
    estresse: a escala e ordinal, nao nominal.
    """
    ruido = gen.normal(0.0, 0.32)
    x = latente + ruido
    return int(np.searchsorted(np.asarray(limiares), x))


def escore_cor(de00):
    """Escore visual de cor a partir do dE00 instrumental.

    A concordancia e imperfeita de proposito: o olho humano nao resolve
    diferencas abaixo do limiar de percepcao (dE ~ 1) e satura em diferencas
    grandes. Permite a analise 'em que faixa visual e colorimetria discordam'.
    """
    if de00 < 0.8:
        return 0
    if de00 < 1.6:
        return 1
    if de00 < 3.0:
        return 2
    if de00 < 6.0:
        return 3
    return 4


# --------------------------------------------------------------------------
# 4. Estagio 1 — Teste Inicial
# --------------------------------------------------------------------------
nomes_familias = list(FAMILIAS)
lotes = []

datas = pd.to_datetime("2024-01-08") + pd.to_timedelta(
    np.sort(rng.integers(0, 540, size=N_LOTES)), unit="D"
)

for i in range(N_LOTES):
    familia = str(rng.choice(nomes_familias))
    cfg = FAMILIAS[familia]
    fornecedor = str(rng.choice(list(FORNECEDORES)))

    # Qualidade latente da emulsao: governa estresse no dia 0 E deriva aos 90 d
    robustez = float(rng.normal(0.0, 1.0) + FORNECEDORES[fornecedor])
    estresse = -robustez  # escores altos = pior emulsao

    ph0 = float(rng.normal(cfg["ph_alvo"], cfg["ph_sd"]) - 0.06 * robustez)
    dens0 = float(rng.normal(cfg["dens_alvo"], cfg["dens_sd"]) - 0.0018 * robustez)

    L0, a0, b0 = cfg["lab_padrao"]
    dL = float(rng.normal(0.0, 0.68) - 0.16 * robustez)
    da = float(rng.normal(0.0, 0.50))
    db = float(rng.normal(0.0, 0.62) - 0.20 * robustez)
    de_lib = delta_e_2000((L0, a0, b0), (L0 + dL, a0 + da, b0 + db))

    s_aspecto = escore_ordinal(estresse * 0.75, rng)
    s_estufa = escore_ordinal(estresse, rng)
    s_centrifuga = escore_ordinal(estresse * 1.10, rng)
    s_agitacao = (escore_ordinal(estresse * 0.85, rng)
                  if cfg["agitacao_aplicavel"] else np.nan)
    odor_ok = bool(rng.random() > 0.02 + 0.05 * max(0.0, estresse) / 3.0)
    s_cor = escore_cor(de_lib)

    lotes.append(dict(
        data_inicio_teste=datas[i],
        lote=f"{cfg['sigla']}-{datas[i]:%y%m}-{i + 1:03d}",
        produto_familia=familia,
        produto_sigla=cfg["sigla"],
        fornecedor_tensoativo=fornecedor,
        robustez_latente=round(robustez, 4),
        aspecto_score=s_aspecto,
        aspecto_desc=escore_para_texto(TXT_ASPECTO, s_aspecto, rng),
        cor_L=round(L0 + dL, 2), cor_a=round(a0 + da, 2), cor_b=round(b0 + db, 2),
        delta_L=round(dL, 3), delta_a=round(da, 3), delta_b=round(db, 3),
        delta_e_liberacao=round(de_lib, 3),
        cor_score=s_cor,
        cor_desc=escore_para_texto(TXT_COR, s_cor, rng),
        odor_conforme=odor_ok,
        odor_desc=escore_para_texto(TXT_ODOR, odor_ok, rng),
        ph=round(ph0, 2),
        densidade_g_cm3=round(dens0, 3),
        estufa50_score=s_estufa,
        estufa50_desc=escore_para_texto(TXT_ESTUFA, s_estufa, rng),
        centrifugacao_score=s_centrifuga,
        centrifugacao_desc=escore_para_texto(TXT_CENTRIFUGA, s_centrifuga, rng),
        agitacao_score=s_agitacao,
        agitacao_desc=(escore_para_texto(TXT_AGITACAO, s_agitacao, rng)
                       if cfg["agitacao_aplicavel"] else "-"),
        analista=str(rng.choice(["ANL-01", "ANL-02", "ANL-03"])),
        instrumento_ph=str(rng.choice(["PH-01", "PH-02"])),
    ))

e1 = pd.DataFrame(lotes)

# --------------------------------------------------------------------------
# 5. Erros de laboratorio injetados (com gabarito separado)
# --------------------------------------------------------------------------
gabarito = []

# (a) sonda de pH descalibrada: PH-02 com offset sistematico em uma janela
janela = (e1.instrumento_ph == "PH-02") & \
         (e1.data_inicio_teste >= "2024-09-01") & (e1.data_inicio_teste < "2024-11-15")
for idx in e1.index[janela]:
    verdadeiro = e1.at[idx, "ph"]
    e1.at[idx, "ph"] = round(verdadeiro + 0.35, 2)
    gabarito.append(dict(lote=e1.at[idx, "lote"], estagio=1, parametro="ph",
                         tipo_erro="sonda_descalibrada",
                         valor_registrado=e1.at[idx, "ph"],
                         valor_verdadeiro=verdadeiro))

# (b) decimal deslocado na digitacao (pH e densidade)
for col, fator in [("ph", 10.0), ("densidade_g_cm3", 10.0)]:
    for idx in rng.choice(e1.index, size=4, replace=False):
        verdadeiro = e1.at[idx, col]
        e1.at[idx, col] = round(verdadeiro * fator, 3)
        gabarito.append(dict(lote=e1.at[idx, "lote"], estagio=1, parametro=col,
                             tipo_erro="decimal_deslocado",
                             valor_registrado=e1.at[idx, col],
                             valor_verdadeiro=verdadeiro))

# (c) replicata trocada: valor de densidade de outro lote entra na linha errada
for idx in rng.choice(e1.index, size=5, replace=False):
    outro = int(rng.choice([j for j in e1.index if j != idx]))
    verdadeiro = e1.at[idx, "densidade_g_cm3"]
    e1.at[idx, "densidade_g_cm3"] = e1.at[outro, "densidade_g_cm3"]
    gabarito.append(dict(lote=e1.at[idx, "lote"], estagio=1,
                         parametro="densidade_g_cm3", tipo_erro="replicata_trocada",
                         valor_registrado=e1.at[idx, "densidade_g_cm3"],
                         valor_verdadeiro=verdadeiro))

df_gabarito = pd.DataFrame(gabarito)

# --------------------------------------------------------------------------
# 6. spec_master versionada, com as excecoes por familia explicitas
# --------------------------------------------------------------------------
spec_rows = []
for familia, cfg in FAMILIAS.items():
    base = dict(produto_familia=familia, vigente_de="2024-01-01",
                vigente_ate="", versao_spec="v1.0")
    spec_rows += [
        dict(**base, ensaio="ph", criterio_tipo="faixa",
             limite_min=cfg["ph_min"], limite_max=cfg["ph_max"],
             excecao_permitida="", justificativa_tecnica="Faixa de estabilidade quimica do sistema"),
        dict(**base, ensaio="densidade_g_cm3", criterio_tipo="faixa",
             limite_min=cfg["dens_min"], limite_max=cfg["dens_max"],
             excecao_permitida="", justificativa_tecnica="Controle de dosagem e ar incorporado"),
        # Unico ensaio com spec revisada no periodo: duas linhas, vigencias
        # distintas. Um resultado de 2024-05 e julgado pela v1.0; um de 2025-02
        # pela v1.1. Junta-se pela data da amostra, nao pela spec atual.
        dict(produto_familia=familia, vigente_de="2024-01-01",
             vigente_ate="2024-09-30", versao_spec="v1.0",
             ensaio="delta_e_liberacao", criterio_tipo="max",
             limite_min="", limite_max=LIM_DELTA_E_LIB_V10, excecao_permitida="",
             justificativa_tecnica="Tolerancia inicial, herdada de avaliacao visual contra padrao"),
        dict(produto_familia=familia, vigente_de="2024-10-01",
             vigente_ate="", versao_spec="v1.1",
             ensaio="delta_e_liberacao", criterio_tipo="max",
             limite_min="", limite_max=LIM_DELTA_E_LIB_V11, excecao_permitida="",
             justificativa_tecnica="Aperto apos implantacao de colorimetro de bancada: dE00 ~1 e o limiar de percepcao visual (ASTM D2244)"),
        dict(**base, ensaio="aspecto_score", criterio_tipo="max",
             limite_min="", limite_max=LIM_ASPECTO, excecao_permitida="",
             justificativa_tecnica="Escore 3+ indica separacao de fase"),
        dict(**base, ensaio="estufa50_score", criterio_tipo="max",
             limite_min="", limite_max=LIM_ESTRESSE, excecao_permitida="",
             justificativa_tecnica="Triagem de estabilidade termica de curto prazo"),
        dict(**base, ensaio="centrifugacao_score", criterio_tipo="max",
             limite_min="",
             limite_max=(LIM_CENTRIFUGA_EXCECAO if cfg["excecao_centrifugacao"]
                         else LIM_ESTRESSE),
             excecao_permitida=cfg["excecao_centrifugacao"] or "",
             justificativa_tecnica="Estresse gravitacional acelerado"),
        dict(**base, ensaio="agitacao_score", criterio_tipo="max",
             limite_min="", limite_max=LIM_ESTRESSE,
             excecao_permitida="" if cfg["agitacao_aplicavel"] else "Ensaio nao aplicavel a familia",
             justificativa_tecnica="Reversibilidade da homogeneizacao"),
        dict(**base, ensaio="odor_conforme", criterio_tipo="booleano",
             limite_min="", limite_max="", excecao_permitida="",
             justificativa_tecnica="Indicador de rancidez e degradacao de fragrancia"),
        # Criterios de ESTABILIDADE (Tx vs T0 do proprio lote). Ficam na spec para
        # que ela seja a unica fonte de verdade: o script 02 nao reimplementa
        # limite nenhum em codigo, le todos daqui.
        dict(**base, ensaio="delta_e_estabilidade", criterio_tipo="max",
             limite_min="", limite_max=LIM_DELTA_E_EST, excecao_permitida="",
             justificativa_tecnica="Deriva de cor aceitavel ao longo do estudo de estabilidade"),
        dict(**base, ensaio="delta_e_estabilidade_luz", criterio_tipo="max",
             limite_min="", limite_max=LIM_DELTA_E_FOTO,
             excecao_permitida="Aplica-se somente a condicao Luz Solar",
             justificativa_tecnica="Endpoint de fotoestabilidade: alteracao de cor sob exposicao solar direta nao e criterio de liberacao (ICH Q1B)"),
    ]
spec_master = pd.DataFrame(spec_rows)

# --------------------------------------------------------------------------
# 7. Portao do Estagio 1 — regra AND explicita sobre a spec vigente
# --------------------------------------------------------------------------
def avaliar_estagio1(row) -> tuple[str, str]:
    cfg = FAMILIAS[row.produto_familia]
    causas = []
    if not (cfg["ph_min"] <= row.ph <= cfg["ph_max"]):
        causas.append("pH fora de faixa")
    if not (cfg["dens_min"] <= row.densidade_g_cm3 <= cfg["dens_max"]):
        causas.append("densidade fora de faixa")
    lim_cor = (LIM_DELTA_E_LIB_V10 if row.data_inicio_teste < DATA_REVISAO_SPEC
               else LIM_DELTA_E_LIB_V11)
    if row.delta_e_liberacao > lim_cor:
        causas.append("cor fora de tolerancia")
    if not row.odor_conforme:
        causas.append("odor alterado")
    if row.aspecto_score > LIM_ASPECTO:
        causas.append("aspecto nao conforme")
    if row.estufa50_score > LIM_ESTRESSE:
        causas.append("falha em estufa 50C")
    # Excecao por familia: onde a spec declara excecao (precipitado fino do
    # estabilizante no alvejante, cremeacao reversivel no amaciante catonico), o
    # escore 3 e aceito — o fenomeno decorre da quimica do sistema e nao indica
    # instabilidade. Sem excecao declarada, 3 reprova.
    lim_centrifuga = (LIM_CENTRIFUGA_EXCECAO if cfg["excecao_centrifugacao"]
                      else LIM_ESTRESSE)
    if row.centrifugacao_score > lim_centrifuga:
        causas.append("falha em centrifugacao")
    if cfg["agitacao_aplicavel"] and row.agitacao_score > LIM_ESTRESSE:
        causas.append("falha em agitacao magnetica")
    return ("Reprovado" if causas else "Aprovado"), "; ".join(causas)

res1 = e1.apply(avaliar_estagio1, axis=1, result_type="expand")
e1["status_estagio1"] = res1[0]
e1["causa_reprovacao_estagio1"] = res1[1]
e1["observacoes"] = np.where(
    (e1.centrifugacao_score == LIM_CENTRIFUGA_EXCECAO)
    & e1.produto_familia.map(lambda f: FAMILIAS[f]["excecao_centrifugacao"] is not None),
    "Aceito conforme excecao de familia na centrifugacao (escore 3)", "",
)

# --------------------------------------------------------------------------
# 8. Dupla avaliacao organoleptica (para kappa de Cohen)
# --------------------------------------------------------------------------
dupla = []
for idx in rng.choice(e1.index, size=int(0.25 * len(e1)), replace=False):
    row = e1.loc[idx]
    for col in ["aspecto_score", "estufa50_score", "centrifugacao_score"]:
        base = row[col]
        if pd.isna(base):
            continue
        # 25% de chance de discordar em +-1 (avaliacao subjetiva)
        desloca = rng.choice([-1, 0, 1], p=[0.12, 0.76, 0.12])
        dupla.append(dict(lote=row.lote, ensaio=col,
                          analista_1=row.analista, escore_analista_1=int(base),
                          analista_2="ANL-04",
                          escore_analista_2=int(np.clip(base + desloca, 0, 4))))
df_dupla = pd.DataFrame(dupla)

# --------------------------------------------------------------------------
# 9. Estagios 2 e 3 — deriva por mecanismo
# --------------------------------------------------------------------------
aprov1 = e1[e1.status_estagio1 == "Aprovado"].copy()

linhas_e2 = []
for row in aprov1.itertuples():
    cfg = FAMILIAS[row.produto_familia]
    # Choque termico: media dos fatores de aceleracao das duas temperaturas,
    # mais um termo de estresse fisico proprio do ciclo (dilata/contrai)
    af_ciclo = 0.5 * (fator_arrhenius(278.15) + fator_arrhenius(313.15))
    estresse_fisico = max(0.0, -row.robustez_latente)
    for t in TEMPOS_E2:
        ph = row.ph - cfg["k_ph"] * af_ciclo * t * np.exp(-0.25 * row.robustez_latente)
        dens = row.densidade_g_cm3 + cfg["k_dens"] * af_ciclo * t
        dL = row.delta_L - cfg["k_cor"] * af_ciclo * t * 0.5
        db = row.delta_b + cfg["k_cor"] * af_ciclo * t
        L0, a0, b0 = cfg["lab_padrao"]
        de = delta_e_2000((L0 + row.delta_L, a0 + row.delta_a, b0 + row.delta_b),
                          (L0 + dL, a0 + row.delta_a, b0 + db))
        s_asp = escore_ordinal(-row.robustez_latente + 0.45 * estresse_fisico * (t / 30.0), rng)
        s_cor = escore_cor(de)
        odor_ok = bool(rng.random() > 0.01 + 0.03 * estresse_fisico)
        linhas_e2.append(dict(
            lote=row.lote, produto_familia=row.produto_familia,
            estagio=2, condicao="Choque Termico 5C/40C", tempo_dias=t,
            ph=round(ph + rng.normal(0, 0.03), 2),
            densidade_g_cm3=round(dens + rng.normal(0, 0.0015), 3),
            delta_e_estabilidade=round(de, 3),
            aspecto_score=s_asp,
            aspecto_desc=escore_para_texto(TXT_ASPECTO, s_asp, rng),
            cor_score=s_cor, cor_desc=escore_para_texto(TXT_COR, s_cor, rng),
            odor_conforme=odor_ok,
            odor_desc=escore_para_texto(TXT_ODOR, odor_ok, rng),
        ))
e2 = pd.DataFrame(linhas_e2)


def oos_estabilidade(row) -> str:
    """Conformidade de uma avaliacao de estabilidade contra a spec da familia.

    O limite de cor depende da condicao: sob luz solar aplica-se o criterio de
    FOTOESTABILIDADE (mais folgado), porque alteracao de cor sob exposicao
    solar direta e um endpoint de estabilidade e nao um criterio de liberacao.
    """
    cfg = FAMILIAS[row.produto_familia]
    lim_cor = LIM_DELTA_E_FOTO if row.condicao == "Luz Solar" else LIM_DELTA_E_EST
    causas = []
    if not (cfg["ph_min"] <= row.ph <= cfg["ph_max"]):
        causas.append("pH fora de faixa")
    if not (cfg["dens_min"] <= row.densidade_g_cm3 <= cfg["dens_max"]):
        causas.append("densidade fora de faixa")
    if row.delta_e_estabilidade > lim_cor:
        causas.append("alteracao de cor")
    if row.aspecto_score > LIM_ASPECTO:
        causas.append("aspecto nao conforme")
    if not row.odor_conforme:
        causas.append("odor alterado")
    return "; ".join(causas)

e2["causa_oos"] = e2.apply(oos_estabilidade, axis=1)
e2["oos_flag"] = e2.causa_oos != ""

# Portao do estagio 2: reprova se houver OOS em qualquer avaliacao (15 ou 30 d)
falhou_e2 = e2.groupby("lote").oos_flag.any()
aprov1["status_estagio2"] = aprov1.lote.map(
    lambda l: "Reprovado" if falhou_e2.get(l, False) else "Aprovado")
aprov1["causa_reprovacao_estagio2"] = aprov1.lote.map(
    lambda l: "; ".join(sorted({c for c in e2.loc[e2.lote == l, "causa_oos"] if c})))

aprov2 = aprov1[aprov1.status_estagio2 == "Aprovado"].copy()

linhas_e3 = []
for row in aprov2.itertuples():
    cfg = FAMILIAS[row.produto_familia]
    ph_ent = float(e2.loc[(e2.lote == row.lote) & (e2.tempo_dias == 30), "ph"].iloc[0])
    dens_ent = float(e2.loc[(e2.lote == row.lote) & (e2.tempo_dias == 30),
                            "densidade_g_cm3"].iloc[0])
    for condicao, (T, dose_rel) in CONDICOES.items():
        af = fator_arrhenius(T)
        for t in TEMPOS_E3:
            # Mecanismo termico: atua em pH e densidade (e pouco na cor)
            ph = ph_ent - cfg["k_ph"] * af * t * np.exp(-0.25 * row.robustez_latente)
            dens = dens_ent + cfg["k_dens"] * af * t
            dL_t = -cfg["k_cor"] * af * t * 0.4
            db_t = cfg["k_cor"] * af * t * 0.8
            # Mecanismo fotoquimico: dependente de DOSE, atua em b* (amarelece)
            # e L* (desbota); praticamente nao mexe no pH
            if dose_rel > 0:
                dose = dose_rel * t
                db_t += cfg["foto"] * 4.8 * (1.0 - np.exp(-dose / 42.0))
                dL_t += -cfg["foto"] * 1.9 * (1.0 - np.exp(-dose / 55.0))
            L0, a0, b0 = cfg["lab_padrao"]
            de = delta_e_2000(
                (L0 + row.delta_L, a0 + row.delta_a, b0 + row.delta_b),
                (L0 + row.delta_L + dL_t, a0 + row.delta_a,
                 b0 + row.delta_b + db_t))
            estresse_t = (-row.robustez_latente
                          + 0.35 * max(0.0, -row.robustez_latente) * af * (t / 90.0))
            s_asp = escore_ordinal(estresse_t, rng)
            s_cor = escore_cor(de)
            odor_ok = bool(rng.random() > 0.008 + 0.02 * af * max(0.0, -row.robustez_latente) / 3)
            linhas_e3.append(dict(
                lote=row.lote, produto_familia=row.produto_familia,
                estagio=3, condicao=condicao, tempo_dias=t,
                ph=round(ph + rng.normal(0, 0.03), 2),
                densidade_g_cm3=round(dens + rng.normal(0, 0.0015), 3),
                delta_L=round(dL_t, 3), delta_a=0.0, delta_b=round(db_t, 3),
                delta_e_estabilidade=round(de, 3),
                aspecto_score=s_asp,
                aspecto_desc=escore_para_texto(TXT_ASPECTO, s_asp, rng),
                cor_score=s_cor, cor_desc=escore_para_texto(TXT_COR, s_cor, rng),
                odor_conforme=odor_ok,
                odor_desc=escore_para_texto(TXT_ODOR, odor_ok, rng),
            ))
e3 = pd.DataFrame(linhas_e3)
e3["causa_oos"] = e3.apply(oos_estabilidade, axis=1)
e3["oos_flag"] = e3.causa_oos != ""

# Desfecho aos 90 dias: conformidade em ambiente escuro (condicao de uso real)
# e nas condicoes de estresse. Alvo do modelo de previsao antecipada.
# Regra de desfecho do Estagio 3, conforme a funcao de cada condicao:
#   Ambiente Escuro 25 C -> condicao de USO: OOS em qualquer ponto reprova
#   Estufa 40 C          -> endpoint ACELERADO: julgado no dia 90
#   Geladeira 5 C        -> CONTROLE negativo: informativo, nao reprova
#   Luz Solar            -> endpoint de FOTOESTABILIDADE, em coluna propria
#                           (nao entra na decisao de estabilidade do lote)
uso = e3[e3.condicao == "Ambiente Escuro 25C"].groupby("lote").oos_flag.any()
acel = (e3[(e3.condicao == "Estufa 40C") & (e3.tempo_dias == 90)]
        .set_index("lote").oos_flag)
foto = (e3[(e3.condicao == "Luz Solar") & (e3.tempo_dias == 90)]
        .set_index("lote").oos_flag)

reprova_e3 = (uso.reindex(aprov2.lote).fillna(False).to_numpy()
              | acel.reindex(aprov2.lote).fillna(False).to_numpy())
aprov2["status_estagio3_90d"] = np.where(reprova_e3, "Reprovado", "Aprovado")
aprov2["fotoestabilidade_90d"] = np.where(
    foto.reindex(aprov2.lote).fillna(False).to_numpy(), "Nao conforme", "Conforme")
causas_dec = (e3[(e3.condicao == "Ambiente Escuro 25C")
                 | ((e3.condicao == "Estufa 40C") & (e3.tempo_dias == 90))]
              .groupby("lote").causa_oos
              .apply(lambda s: "; ".join(sorted({c for v in s for c in v.split("; ") if c}))))
aprov2["causa_reprovacao_estagio3"] = causas_dec.reindex(aprov2.lote).fillna("").to_numpy()

# Consolidado do funil
funil = e1[["lote", "data_inicio_teste", "produto_familia", "produto_sigla",
            "fornecedor_tensoativo", "status_estagio1",
            "causa_reprovacao_estagio1"]].copy()
funil = funil.merge(
    aprov1[["lote", "status_estagio2", "causa_reprovacao_estagio2"]], on="lote", how="left")
funil = funil.merge(
    aprov2[["lote", "status_estagio3_90d", "causa_reprovacao_estagio3",
            "fotoestabilidade_90d"]], on="lote", how="left")
funil["estagio_final"] = np.select(
    [funil.status_estagio1 == "Reprovado",
     funil.status_estagio2 == "Reprovado",
     funil.status_estagio3_90d == "Reprovado"],
    ["Reprovado no Teste Inicial", "Reprovado na Estabilidade Preliminar",
     "Reprovado na Estabilidade Acelerada"],
    default="Aprovado aos 90 dias")
funil["sobreviveu_90d"] = funil.estagio_final == "Aprovado aos 90 dias"

# --------------------------------------------------------------------------
# 10. Gravacao
# --------------------------------------------------------------------------
OUT_DIR.mkdir(parents=True, exist_ok=True)
e1.drop(columns=["robustez_latente"]).to_csv(
    OUT_DIR / "estagio1_teste_inicial.csv", index=False, encoding="utf-8")
e2.to_csv(OUT_DIR / "estagio2_estabilidade_preliminar.csv", index=False, encoding="utf-8")
e3.to_csv(OUT_DIR / "estagio3_estabilidade_acelerada.csv", index=False, encoding="utf-8")
funil.to_csv(OUT_DIR / "funil_lotes.csv", index=False, encoding="utf-8")
spec_master.to_csv(OUT_DIR / "spec_master.csv", index=False, encoding="utf-8")
fam_meta = pd.DataFrame([
    dict(sigla=c["sigla"], produto_familia=f, classificacao_anvisa=c["anvisa"],
         ph_min=c["ph_min"], ph_alvo=c["ph_alvo"], ph_max=c["ph_max"],
         densidade_min=c["dens_min"], densidade_alvo=c["dens_alvo"], densidade_max=c["dens_max"],
         agitacao_magnetica_aplicavel=c["agitacao_aplicavel"],
         excecao_centrifugacao=c["excecao_centrifugacao"] or "",
         fonte_faixa_ph=c["fonte_ph"])
    for f, c in FAMILIAS.items()])
fam_meta.to_csv(OUT_DIR / "familias_produto.csv", index=False, encoding="utf-8")

df_dupla.to_csv(OUT_DIR / "avaliacao_duplicada_analistas.csv", index=False, encoding="utf-8")
df_gabarito.to_csv(OUT_DIR / "gabarito_erros_injetados.csv", index=False, encoding="utf-8")

print(f"estagio1: {len(e1)} lotes | estagio2: {len(e2)} avaliacoes "
      f"| estagio3: {len(e3)} avaliacoes")
print(funil.estagio_final.value_counts().to_string())
