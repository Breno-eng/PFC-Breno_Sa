"""
Análise completa — Keras vs Aspen
Gera 5 figuras salvas diretamente na pasta, sem abrir janelas.

Figuras geradas:
  1. acetileno_fracao_molar.png         — Previsto vs Real + Erro por faixa + Viés
  2. erros_por_grupo.png                — Onde o modelo erra mais por grupo
  3. tolerancias_por_grupo.png          — Curvas + heatmap por grupo
  4. tolerancias_por_componente.png     — Curvas + heatmap por componente
  5. substituicao_aspen.png             — Tolerância vs % substituível vs ganho de velocidade

Dependências: pip install pandas numpy matplotlib seaborn
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import warnings
import os
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CAMINHOS — ajuste aqui se necessário
# ─────────────────────────────────────────────
CAMINHO_CSV = r"C:\DigitalTwin\Backup\resultados\relatorio_producao_sem_bias_20260316_074347.csv"
PASTA_SAIDA = r"C:\DigitalTwin\Backup\Modelos Keras"
os.makedirs(PASTA_SAIDA, exist_ok=True)

def salvar(nome):
    caminho = os.path.join(PASTA_SAIDA, nome)
    plt.savefig(caminho, bbox_inches='tight', dpi=130)
    plt.close()
    print(f"✓ Salvo: {caminho}")

# ─────────────────────────────────────────────
# CONFIGURAÇÃO VISUAL
# ─────────────────────────────────────────────
plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor':   '#F9F9F7',
    'axes.grid':        True,
    'grid.alpha':       0.35,
    'grid.linewidth':   0.5,
    'font.family':      'DejaVu Sans',
    'font.size':        12,
    'axes.titlesize':   13,
    'axes.titleweight': 'bold',
    'axes.labelsize':   12,
    'xtick.labelsize':  11,
    'ytick.labelsize':  11,
    'legend.fontsize':  11,
})

AZUL    = '#185FA5'
VERDE   = '#1D9E75'
LARANJA = '#D85A30'
ROXO    = '#534AB7'
AMBAR   = '#BA7517'
CINZA   = '#888780'
CORES_GRUPO = [AZUL, VERDE, LARANJA, ROXO, AMBAR, CINZA, '#993556']
TOLERANCIAS = [1, 2, 5, 10, 20]

# ─────────────────────────────────────────────
# CARREGAMENTO E LIMPEZA
# ─────────────────────────────────────────────
df = pd.read_csv(CAMINHO_CSV)
df['erro_pct']   = pd.to_numeric(df['erro_pct'],   errors='coerce').abs()
df['erro_abs']   = pd.to_numeric(df['erro_abs'],   errors='coerce').abs()
df['aspen']      = pd.to_numeric(df['aspen'],      errors='coerce')
df['keras']      = pd.to_numeric(df['keras'],      errors='coerce')
df['tempo_total']= pd.to_numeric(df['tempo_total'],errors='coerce')

df_clean = df[df['erro_pct'] < 1000].copy()

print(f"Registros carregados : {len(df)}")
print(f"Após filtro outliers : {len(df_clean)}")

# ─────────────────────────────────────────────
# CLASSIFICAÇÕES
# ─────────────────────────────────────────────
def grupo_variavel(v):
    if 'MOLEFRAC' in v or 'MASSFRAC' in v: return 'Composição (frações)'
    if any(x in v for x in ['_B_TEMP','RES_TEMP','TMIN','TMAX','_TOS']): return 'Temperatura'
    if any(x in v for x in ['_B_PRES','RES_PRES','_POC']): return 'Pressão'
    if 'QCALC' in v: return 'Calor trocado'
    if any(x in v for x in ['VOLFLOW','MASSFLOW','MOLEFLOW','TOT_FLOW','BAL_MOL']): return 'Vazões e balanços'
    if 'RES_TIME' in v: return 'Tempo de residência'
    if 'WNET' in v: return 'Trabalho líquido'
    return 'Outros'

def componente(v):
    if 'ACETA' in v: return 'Acetileno'
    if 'ETHYL' in v: return 'Etileno'
    if 'OXYGE' in v: return 'Oxigênio'
    if 'N2'    in v: return 'Nitrogênio'
    return 'Outros'

df_clean['grupo']      = df_clean['variavel'].apply(grupo_variavel)
df_clean['componente'] = df_clean['variavel'].apply(componente)

# Ordem dos grupos por mediana do erro (do maior para o menor)
ordem_grupos = (df_clean.groupby('grupo')['erro_pct']
                .median()
                .sort_values(ascending=False)
                .index.tolist())


# ══════════════════════════════════════════════════════════════
# FIGURA 1 — Fração molar do acetileno: Previsto vs Real
# ══════════════════════════════════════════════════════════════
print("\nGerando figura 1...")

# Somente a variável crítica — todas as simulações disponíveis
df_all = df[df['erro_pct'] < 1000].copy()  # sem filtro de conjunto
mask_aceta = df_all['variavel'] == 'PRODUTO_ACETA-01_MOLEFRAC_MIXED'
df_aceta = df_all[mask_aceta].copy()

# Faixas alinhadas com o balanceamento do TCC (Tabela 4.1.3)
bins_faixa   = [0, 0.30, 0.50, 0.70, 0.90, 1.01]
labels_faixa = ['[0.0 – 0.30)', '[0.30 – 0.50)', '[0.50 – 0.70)', '[0.70 – 0.90)', '[0.90 – 1.00]']
df_aceta['faixa'] = pd.cut(df_aceta['aspen'].clip(0, 1),
                            bins=bins_faixa, labels=labels_faixa)

CORES_FAIXA = {
    '[0.0 – 0.30)':  '#A32D2D',
    '[0.30 – 0.50)': '#D85A30',
    '[0.50 – 0.70)': '#BA7517',
    '[0.70 – 0.90)': '#1D9E75',
    '[0.90 – 1.00]': '#185FA5',
}

fig, axes = plt.subplots(1, 3, figsize=(18, 6))
fig.suptitle('Fração molar do acetileno — Keras vs Aspen', fontsize=13, y=0.98)

# Painel A — Previsto vs Real
ax = axes[0]
for faixa, cor in CORES_FAIXA.items():
    sub = df_aceta[df_aceta['faixa'] == faixa]
    if len(sub) == 0:
        continue
    ax.scatter(sub['aspen'], sub['keras'], color=cor, s=20, alpha=0.5,
               label=f"{faixa}  (n={sub['caso_id'].nunique():,} casos)", zorder=3)
lim_min = df_aceta[['aspen','keras']].min().min() - 0.02
lim_max = df_aceta[['aspen','keras']].max().max() + 0.02
ax.plot([lim_min, lim_max], [lim_min, lim_max],
        '--', color=CINZA, linewidth=1.5, label='Predição perfeita', zorder=2)
ax.set_xlabel('Valor real (Aspen)')
ax.set_ylabel('Valor previsto (Keras)')
ax.set_title('Previsto vs Real')
ax.legend(fontsize=9)
ax.set_xlim(lim_min, lim_max)
ax.set_ylim(lim_min, lim_max)

# Painel B — Erro % por faixa (eixo Y limitado a 20%, outliers marcados com triângulo)
ax = axes[1]
ordem_f = [l for l in labels_faixa if l in df_aceta['faixa'].cat.categories.tolist()]
cores_ordem = [CORES_FAIXA[f] for f in ordem_f]
CAP_Y = 20

bp = ax.boxplot(
    [df_aceta[df_aceta['faixa'] == f]['erro_pct'].values for f in ordem_f],
    patch_artist=True,
    showfliers=False,
    medianprops=dict(color='white', linewidth=2),
    widths=0.55,
)
for patch, cor in zip(bp['boxes'], cores_ordem):
    patch.set_facecolor(cor)
    patch.set_alpha(0.85)

for i, f in enumerate(ordem_f):
    vals = df_aceta[df_aceta['faixa'] == f]['erro_pct']
    outliers = vals[vals > CAP_Y]
    if len(outliers) > 0:
        ax.scatter([i + 1] * len(outliers), [CAP_Y * 0.97] * len(outliers),
                   marker='^', color=CORES_FAIXA[f], s=18, alpha=0.6, zorder=4)
    med = vals.median()
    ax.text(i + 1, med + 0.3, f'{med:.1f}%',
            ha='center', va='bottom', fontsize=10, fontweight='bold')

ax.set_ylim(0, CAP_Y)
ax.set_xticks(range(1, len(ordem_f) + 1))
ax.set_xticklabels(ordem_f, fontsize=10, rotation=15, ha='right')
ax.set_ylabel('Erro percentual (%)')
ax.set_title('Erro % por faixa\n(outliers >20% indicados com ▲)')
ax.axhline(5, color=LARANJA, linestyle=':', linewidth=1.2, label='5% tolerância')
ax.legend(fontsize=10)

# Painel C — Viés por faixa
ax = axes[2]
df_aceta['vies'] = df_aceta['keras'] - df_aceta['aspen']
for i, (faixa, cor) in enumerate(zip(ordem_f, cores_ordem)):
    sub = df_aceta[df_aceta['faixa'] == faixa]['vies']
    sub_plot = sub.sample(min(len(sub), 300), random_state=42)
    ax.scatter([i + 1] * len(sub_plot), sub_plot,
               color=cor, alpha=0.35, s=18, zorder=3)
    ax.plot([i + 0.7, i + 1.3], [sub.mean(), sub.mean()],
            color=cor, linewidth=2.5, zorder=4)
ax.axhline(0, color=CINZA, linewidth=1.5, linestyle='--', label='Sem viés')
ax.set_xticks(range(1, len(ordem_f) + 1))
ax.set_xticklabels(ordem_f, fontsize=10, rotation=15, ha='right')
ax.set_ylabel('Viés  (Keras − Aspen)')
ax.set_title('Viés por faixa')
ax.legend(fontsize=10)

plt.tight_layout()
salvar('acetileno_fracao_molar.png')


# ══════════════════════════════════════════════════════════════
# FIGURA 2 — Onde o modelo erra mais: barras + taxa de acerto
# ══════════════════════════════════════════════════════════════
print("Gerando figura 2...")

grp_stats = (df_clean.groupby('grupo')['erro_pct']
             .agg(
                 media   = 'mean',
                 mediana = 'median',
                 p90     = lambda x: np.percentile(x, 90),
                 n       = 'count',
                 pct_ok  = lambda x: (x <= 5).mean() * 100,
             )
             .reindex(ordem_grupos)
             .reset_index())

cores_g = [CORES_GRUPO[i % len(CORES_GRUPO)] for i in range(len(grp_stats))]

fig, axes = plt.subplots(1, 2, figsize=(17, 6))
fig.suptitle('Erro por grupo de variável', fontsize=13, y=0.98)

# Painel A — Barras: média, mediana, P90
ax = axes[0]
y = np.arange(len(grp_stats))
h = 0.25
ax.barh(y + h,  grp_stats['media'],   h, color=[c+'CC' for c in cores_g],
        edgecolor='white', label='Média')
ax.barh(y,      grp_stats['mediana'], h, color=cores_g,
        edgecolor='white', label='Mediana')
ax.barh(y - h,  grp_stats['p90'],     h, color=[c+'55' for c in cores_g],
        edgecolor='white', label='P90 (pior 10%)')
ax.set_yticks(y)
ax.set_yticklabels(grp_stats['grupo'], fontsize=11)
ax.set_xlabel('Erro percentual (%)')
ax.set_title('Erro % por grupo')
ax.axvline(5, color=LARANJA, linestyle=':', linewidth=1.2, label='5% tolerância')
ax.legend(fontsize=10)
for bar, val in zip(ax.patches[len(grp_stats):2*len(grp_stats)], grp_stats['mediana']):
    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
            f'{val:.1f}%', va='center', fontsize=9)

# Painel B — Taxa de acerto com 5%
ax = axes[1]
grp_ok = grp_stats.sort_values('pct_ok', ascending=True)
cores_ok = [VERDE if v >= 80 else AMBAR if v >= 60 else LARANJA for v in grp_ok['pct_ok']]
bars = ax.barh(range(len(grp_ok)), grp_ok['pct_ok'],
               color=cores_ok, edgecolor='white', height=0.6)
for bar, row in zip(bars, grp_ok.itertuples()):
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f'{row.pct_ok:.0f}%  (n={row.n:,} predições)', va='center', fontsize=10)
ax.set_yticks(range(len(grp_ok)))
ax.set_yticklabels(grp_ok['grupo'], fontsize=11)
ax.set_xlabel('% de predições individuais com erro ≤ 5%')
ax.set_title('Taxa de acerto por grupo')
ax.set_xlim(0, 115)
ax.axvline(80, color=VERDE,   linestyle=':', linewidth=1.2)
ax.axvline(60, color=LARANJA, linestyle=':', linewidth=1.2)
p1 = mpatches.Patch(color=VERDE,   label='≥ 80% — Bom')
p2 = mpatches.Patch(color=AMBAR,   label='60–80% — Atenção')
p3 = mpatches.Patch(color=LARANJA, label='< 60% — Ruim')
ax.legend(handles=[p1, p2, p3], fontsize=10, loc='lower right')

plt.tight_layout()
salvar('erros_por_grupo.png')


# ══════════════════════════════════════════════════════════════
# FIGURA 3 — Tolerâncias por grupo: curvas + heatmap
# ══════════════════════════════════════════════════════════════
print("Gerando figura 3...")

tabela_grupo = {}
for g in ordem_grupos:
    sub = df_clean[df_clean['grupo'] == g]['erro_pct']
    tabela_grupo[g] = {t: (sub <= t).mean() * 100 for t in TOLERANCIAS}

fig, axes = plt.subplots(1, 2, figsize=(16, 7))
fig.suptitle('Taxa de acerto por tolerância — grupos', fontsize=13, y=0.98)

# Painel A — Curvas
ax = axes[0]
for i, g in enumerate(ordem_grupos):
    valores = [tabela_grupo[g][t] for t in TOLERANCIAS]
    ax.plot(TOLERANCIAS, valores, 'o-',
            color=CORES_GRUPO[i % len(CORES_GRUPO)],
            linewidth=2, markersize=7, label=g)
    ax.text(20.4, valores[-1], f'{valores[-1]:.0f}%',
            va='center', fontsize=9, color=CORES_GRUPO[i % len(CORES_GRUPO)])
ax.axhline(90, color=CINZA, linestyle=':', linewidth=1, alpha=0.7)
ax.text(0.8, 91, 'meta 90%', color=CINZA, fontsize=9)
ax.set_xlabel('Tolerância de erro aceita (%)')
ax.set_ylabel('% de predições com erro ≤ tolerância')
ax.set_title('Evolução por tolerância')
ax.set_xticks(TOLERANCIAS)
ax.set_xticklabels([f'{t}%' for t in TOLERANCIAS])
ax.set_ylim(0, 105)
ax.legend(fontsize=10, loc='lower right')

# Painel B — Heatmap
ax = axes[1]
matrix_g = pd.DataFrame(
    {f'{t}%': [tabela_grupo[g][t] for g in ordem_grupos] for t in TOLERANCIAS},
    index=ordem_grupos
)
sns.heatmap(matrix_g, ax=ax, annot=True, fmt='.0f',
            cmap='RdYlGn', vmin=50, vmax=100,
            linewidths=0.5, linecolor='white',
            annot_kws={'size': 11, 'weight': 'bold'},
            cbar_kws={'label': '% dentro da tolerância'})
ax.set_title('Heatmap — grupos × tolerância')
ax.set_xlabel('Tolerância aceita')
ax.set_ylabel('')
ax.tick_params(axis='y', labelsize=11)
ax.tick_params(axis='x', labelsize=11)

plt.tight_layout()
salvar('tolerancias_por_grupo.png')


# ══════════════════════════════════════════════════════════════
# FIGURA 4 — Tolerâncias por componente (só frações)
# ══════════════════════════════════════════════════════════════
print("Gerando figura 4...")

df_frac = df_clean[df_clean['grupo'] == 'Composição (frações)'].copy()
ordem_comp = (df_frac.groupby('componente')['erro_pct']
              .median()
              .sort_values(ascending=False)
              .index.tolist())

tabela_comp = {}
for c in ordem_comp:
    sub = df_frac[df_frac['componente'] == c]['erro_pct']
    tabela_comp[c] = {t: (sub <= t).mean() * 100 for t in TOLERANCIAS}

CORES_COMP = [AZUL, LARANJA, VERDE, ROXO, AMBAR]

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle('Taxa de acerto por tolerância — componentes', fontsize=13, y=0.98)

# Painel A — Curvas
ax = axes[0]
for i, c in enumerate(ordem_comp):
    valores = [tabela_comp[c][t] for t in TOLERANCIAS]
    n_casos = df_frac[df_frac['componente'] == c]['caso_id'].nunique()
    ax.plot(TOLERANCIAS, valores, 'o-',
            color=CORES_COMP[i % len(CORES_COMP)],
            linewidth=2, markersize=7, label=f'{c}  (n={n_casos:,} casos)')
    ax.text(20.4, valores[-1], f'{valores[-1]:.0f}%',
            va='center', fontsize=9, color=CORES_COMP[i % len(CORES_COMP)])
ax.axhline(90, color=CINZA, linestyle=':', linewidth=1, alpha=0.7)
ax.text(0.8, 91, 'meta 90%', color=CINZA, fontsize=9)
ax.set_xlabel('Tolerância de erro aceita (%)')
ax.set_ylabel('% de predições com erro ≤ tolerância')
ax.set_title('Evolução por tolerância')
ax.set_xticks(TOLERANCIAS)
ax.set_xticklabels([f'{t}%' for t in TOLERANCIAS])
ax.set_ylim(0, 105)
ax.legend(fontsize=10)

# Painel B — Heatmap
ax = axes[1]
matrix_c = pd.DataFrame(
    {f'{t}%': [tabela_comp[c][t] for c in ordem_comp] for t in TOLERANCIAS},
    index=ordem_comp
)
sns.heatmap(matrix_c, ax=ax, annot=True, fmt='.0f',
            cmap='RdYlGn', vmin=50, vmax=100,
            linewidths=0.5, linecolor='white',
            annot_kws={'size': 12, 'weight': 'bold'},
            cbar_kws={'label': '% dentro da tolerância'})
ax.set_title('Heatmap — componentes × tolerância')
ax.set_xlabel('Tolerância aceita')
ax.set_ylabel('')
ax.tick_params(axis='y', labelsize=11)
ax.tick_params(axis='x', labelsize=11)

plt.tight_layout()
salvar('tolerancias_por_componente.png')

# ─────────────────────────────────────────────
# RESUMO FINAL NO CONSOLE
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("Todos os gráficos gerados com sucesso!")
print(f"Salvos em: {PASTA_SAIDA}")