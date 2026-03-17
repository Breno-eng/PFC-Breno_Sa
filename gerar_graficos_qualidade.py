"""
Gráficos — Filtro de Qualidade de Outputs (criar_metricas.py)
Salva os gráficos como PNG na mesma pasta do CSV.

Dependências: pip install pandas matplotlib
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from collections import Counter

# ── CONFIGURAÇÃO ─────────────────────────────────────────────
CSV_PATH     = r"C:\DigitalTwin\Backup\Modelos Keras\Metricas de Qualidade\colunas_recomendadas_remover.csv"
DATASET_PATH = r"C:\DigitalTwin\Backup\datasets_gerados\dataset_unificado.csv"
OUTPUT_DIR   = Path(CSV_PATH).parent
DPI          = 180

plt.rcParams.update({
    "font.family":       "sans-serif",
    "font.size":         10,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "grid.linestyle":    "--",
    "figure.dpi":        DPI,
})

# ── CALCULAR TOTAL DE OUTPUTS DO DATASET REAL ─────────────────
META = {"ID", "ID_original", "timestamp", "tempo_simulacao", "instancia", "fonte_dados"}
INPUTS = {
    "AR_TOTFLOW", "AR_TEMP", "AR_PRES",
    "ETILENO_TOTFLOW", "ETILENO_TEMP", "ETILENO_PRES",
    "C-202_PRES", "E-101_TEMP", "E-101_PRES",
    "E-203_TEMP", "E-203_PRES", "E-204_TEMP", "E-204_PRES",
    "R-101_LENGTH", "T-203_TEMP", "T-203_PRES",
    "T-204_BASIS_RR", "T-204_NSTAGE", "T-204_FEED_STAGE",
}

cols_dataset  = pd.read_csv(DATASET_PATH, nrows=0).columns.tolist()
TOTAL_OUTPUTS = len([c for c in cols_dataset if c not in META and c not in INPUTS])

# ── CARREGAR CSV DE REMOVIDOS ─────────────────────────────────
df        = pd.read_csv(CSV_PATH)
REMOVIDOS = len(df)
APROVADOS = TOTAL_OUTPUTS - REMOVIDOS

print(f"Colunas no dataset:  {len(cols_dataset)}")
print(f"  - Metadados:       {len(META)}")
print(f"  - Inputs:          {len(INPUTS)}")
print(f"  = Outputs totais:  {TOTAL_OUTPUTS}")
print(f"  - Removidos:       {REMOVIDOS}")
print(f"  = Aprovados:       {APROVADOS}\n")

# ── PREPARAR DADOS ────────────────────────────────────────────
def get_componente(nome):
    for comp in ["MEA", "DEA", "H2O", "N2", "O2", "ETILENO", "ACETA", "C2H4"]:
        if comp in nome.upper():
            return comp
    return "OUTRO"

def get_tipo(nome):
    for t in ["MOLEFRAC", "MOLEFLOW", "MASSFLOW", "MASSFRAC", "TEMP", "PRES"]:
        if t in nome.upper():
            return t
    return "OUTRO"

df["componente"] = df["coluna"].apply(get_componente)
df["tipo"]       = df["coluna"].apply(get_tipo)

all_problems = []
for p in df["problemas"].dropna():
    all_problems.extend([x.strip() for x in str(p).split(",")])

TRAD_PROB = {
    "BAIXA_ENTROPIA":                   "Baixa entropia",
    "VARIANCIA_BAIXA":                  "Variância baixa",
    "VALOR_DOMINANTE_EXTREMO":          "Valor dominante extremo",
    "CV_EXTREMAMENTE_BAIXO":            "CV extremamente baixo",
    "RANGE_PRATICAMENTE_ZERO":          "Range ≈ zero",
    "POUQUISSIMOS_VALORES":             "Pouquíssimos valores únicos",
    "QUASE_TODOS_ZEROS":                "Quase todos zeros (>80%)",
    "OUTLIERS_EXTREMOS":                "Outliers extremos",
    "VALORES_MUITO_CONCENTRADOS":       "Valores muito concentrados",
    "DISTRIBUICAO_MUITO_ASSIMETRICA":   "Distribuição muito assimétrica",
    "DISTRIBUICAO_MULTIPLOS_PROBLEMAS": "Múltiplos problemas",
    "MUITOS_OUTLIERS":                  "Muitos outliers",
    "OUTLIERS_CRITICOS":                "Outliers críticos",
    "MAIORIA_ZEROS":                    "Maioria zeros (>50%)",
    "CV_MUITO_BAIXO":                   "CV muito baixo",
}

prob_cnt = Counter({TRAD_PROB.get(k, k): v
                    for k, v in Counter(all_problems).items()})
prob_df  = pd.DataFrame(prob_cnt.most_common(),
                        columns=["criterio", "n"]).sort_values("n")

comp_vc  = df["componente"].value_counts()
tipo_vc  = df["tipo"].value_counts()
nprob_vc = df["n_problemas"].value_counts().sort_index()
TOTAL    = len(df)

# ── PALETA ────────────────────────────────────────────────────
CINZA = "#595959"
COMP_COLORS = {
    "MEA": "#1F4E79", "DEA": "#2E75B6", "H2O": "#BA7517",
    "N2":  "#534AB7", "ACETA": "#993C1D", "ETILENO": "#D4537E",
    "O2":  "#1D9E75", "C2H4": "#0F6E56",  "OUTRO": "#888780",
}
TIPO_COLORS = {
    "MOLEFRAC": "#1F4E79", "MOLEFLOW": "#2E75B6",
    "MASSFLOW": "#534AB7", "MASSFRAC": "#BA7517",
    "TEMP":     "#D85A30", "PRES":     "#D4537E",
    "OUTRO":    "#888780",
}

# ─────────────────────────────────────────────────────────────
# FIGURA 1 — Frequência dos critérios de reprovação
# ─────────────────────────────────────────────────────────────
fig1, ax1 = plt.subplots(figsize=(10, 6))
intensidades = prob_df["n"] / prob_df["n"].max()
cores = [plt.cm.Blues(0.35 + 0.55 * i) for i in intensidades]
bars = ax1.barh(prob_df["criterio"], prob_df["n"],
                color=cores, edgecolor="white", linewidth=0.5)
for bar, v in zip(bars, prob_df["n"]):
    pct = v / TOTAL * 100
    ax1.text(bar.get_width() + 2, bar.get_y() + bar.get_height() / 2,
             f"{v}  ({pct:.0f}%)", va="center", fontsize=9, color=CINZA)
ax1.set_xlabel("Número de outputs com o critério", fontsize=10)
ax1.set_title(f"Critérios de reprovação — {TOTAL} outputs removidos",
              fontsize=12, fontweight="bold", pad=14)
ax1.set_xlim(0, prob_df["n"].max() * 1.22)
ax1.tick_params(axis="y", labelsize=9)
plt.tight_layout()
fig1.savefig(OUTPUT_DIR / "fig1_criterios_reprovacao.png", dpi=DPI, bbox_inches="tight")
plt.close(fig1)
print("✓ fig1_criterios_reprovacao.png")

# ─────────────────────────────────────────────────────────────
# FIGURA 2 — Outputs removidos por componente químico
# ─────────────────────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(8, 5))
comps  = comp_vc.index.tolist()
vals   = comp_vc.values
colors = [COMP_COLORS.get(c, "#888780") for c in comps]
bars2 = ax2.bar(comps, vals, color=colors, edgecolor="white", linewidth=0.6)
for bar, v in zip(bars2, vals):
    pct = v / TOTAL * 100
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
             f"{v}\n({pct:.0f}%)", ha="center", va="bottom", fontsize=9, color=CINZA)
ax2.set_ylabel("Número de outputs removidos", fontsize=10)
ax2.set_xlabel("Componente químico", fontsize=10)
ax2.set_title("Outputs removidos por componente químico",
              fontsize=12, fontweight="bold", pad=14)
ax2.set_ylim(0, vals.max() * 1.20)
plt.tight_layout()
fig2.savefig(OUTPUT_DIR / "fig2_componente_quimico.png", dpi=DPI, bbox_inches="tight")
plt.close(fig2)
print("✓ fig2_componente_quimico.png")

# ─────────────────────────────────────────────────────────────
# FIGURA 3 — Outputs removidos por tipo de variável
# ─────────────────────────────────────────────────────────────
fig3, ax3 = plt.subplots(figsize=(8, 5))
tipos   = tipo_vc.index.tolist()
tvals   = tipo_vc.values
tcolors = [TIPO_COLORS.get(t, "#888780") for t in tipos]
bars3 = ax3.bar(tipos, tvals, color=tcolors, edgecolor="white", linewidth=0.6)
for bar, v in zip(bars3, tvals):
    pct = v / TOTAL * 100
    ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
             f"{v}\n({pct:.0f}%)", ha="center", va="bottom", fontsize=9, color=CINZA)
ax3.set_ylabel("Número de outputs removidos", fontsize=10)
ax3.set_xlabel("Tipo de variável", fontsize=10)
ax3.set_title("Outputs removidos por tipo de variável",
              fontsize=12, fontweight="bold", pad=14)
ax3.set_ylim(0, tvals.max() * 1.20)
plt.tight_layout()
fig3.savefig(OUTPUT_DIR / "fig3_tipo_variavel.png", dpi=DPI, bbox_inches="tight")
plt.close(fig3)
print("✓ fig3_tipo_variavel.png")

# ─────────────────────────────────────────────────────────────
# FIGURA 4 — Distribuição por nº de critérios violados
# ─────────────────────────────────────────────────────────────
fig4, ax4 = plt.subplots(figsize=(7, 4))
nprob_x = nprob_vc.index.astype(str) + " critérios"
nprob_y = nprob_vc.values
ramp = [plt.cm.RdYlBu_r(0.15 + 0.75 * i / (len(nprob_y) - 1))
        for i in range(len(nprob_y))]
bars4 = ax4.bar(nprob_x, nprob_y, color=ramp, edgecolor="white", linewidth=0.6)
for bar, v in zip(bars4, nprob_y):
    pct = v / TOTAL * 100
    ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8,
             f"{v}\n({pct:.0f}%)", ha="center", va="bottom", fontsize=9, color=CINZA)
ax4.set_ylabel("Número de outputs", fontsize=10)
ax4.set_xlabel("Quantidade de critérios violados simultaneamente", fontsize=10)
ax4.set_title("Distribuição por quantidade de critérios violados",
              fontsize=12, fontweight="bold", pad=14)
ax4.set_ylim(0, nprob_y.max() * 1.20)
plt.tight_layout()
fig4.savefig(OUTPUT_DIR / "fig4_n_criterios_violados.png", dpi=DPI, bbox_inches="tight")
plt.close(fig4)
print("✓ fig4_n_criterios_violados.png")

# ─────────────────────────────────────────────────────────────
# FIGURA 5 — Painel 2×2 (resumo para o TCC)
# ─────────────────────────────────────────────────────────────
fig5, axes = plt.subplots(2, 2, figsize=(14, 10))
fig5.suptitle(
    f"Análise de qualidade dos outputs — {TOTAL} de {TOTAL_OUTPUTS} removidos "
    f"({TOTAL/TOTAL_OUTPUTS*100:.0f}%)  ·  {APROVADOS} aprovados",
    fontsize=13, fontweight="bold", y=1.01
)

ax = axes[0, 0]
cores_a = [plt.cm.Blues(0.35 + 0.55 * i) for i in prob_df["n"] / prob_df["n"].max()]
bh = ax.barh(prob_df["criterio"], prob_df["n"],
             color=cores_a, edgecolor="white", linewidth=0.4)
for bar, v in zip(bh, prob_df["n"]):
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
            str(v), va="center", fontsize=8, color=CINZA)
ax.set_xlim(0, prob_df["n"].max() * 1.18)
ax.set_title("(a) Critérios de reprovação", fontweight="bold", fontsize=10)
ax.tick_params(axis="y", labelsize=8)
ax.grid(axis="x", alpha=0.3, linestyle="--")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

ax = axes[0, 1]
colors_b = [COMP_COLORS.get(c, "#888780") for c in comp_vc.index]
bv = ax.bar(comp_vc.index, comp_vc.values,
            color=colors_b, edgecolor="white", linewidth=0.4)
for bar, v in zip(bv, comp_vc.values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
            f"{v}", ha="center", va="bottom", fontsize=8, color=CINZA)
ax.set_title("(b) Por componente químico", fontweight="bold", fontsize=10)
ax.set_ylabel("Outputs removidos", fontsize=9)
ax.set_ylim(0, comp_vc.values.max() * 1.18)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

ax = axes[1, 0]
colors_c = [TIPO_COLORS.get(t, "#888780") for t in tipo_vc.index]
bv2 = ax.bar(tipo_vc.index, tipo_vc.values,
             color=colors_c, edgecolor="white", linewidth=0.4)
for bar, v in zip(bv2, tipo_vc.values):
    pct = v / TOTAL * 100
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
            f"{v}\n({pct:.0f}%)", ha="center", va="bottom", fontsize=8, color=CINZA)
ax.set_title("(c) Por tipo de variável", fontweight="bold", fontsize=10)
ax.set_ylabel("Outputs removidos", fontsize=9)
ax.set_ylim(0, tipo_vc.values.max() * 1.30)
ax.tick_params(axis="x", labelsize=8, rotation=30)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

ax = axes[1, 1]
ramp2 = [plt.cm.RdYlBu_r(0.15 + 0.75 * i / (len(nprob_vc) - 1))
         for i in range(len(nprob_vc))]
xlabels = [str(k) for k in nprob_vc.index]
bv3 = ax.bar(xlabels, nprob_vc.values,
             color=ramp2, edgecolor="white", linewidth=0.4)
for bar, v in zip(bv3, nprob_vc.values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
            f"{v}", ha="center", va="bottom", fontsize=8, color=CINZA)
ax.set_title("(d) Critérios violados simultaneamente", fontweight="bold", fontsize=10)
ax.set_xlabel("Nº de critérios violados", fontsize=9)
ax.set_ylabel("Outputs removidos", fontsize=9)
ax.set_ylim(0, nprob_vc.values.max() * 1.18)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
fig5.savefig(OUTPUT_DIR / "fig5_painel_completo.png", dpi=DPI, bbox_inches="tight")
plt.close(fig5)
print("✓ fig5_painel_completo.png")

print(f"\nTodos os gráficos salvos em:\n{OUTPUT_DIR}")