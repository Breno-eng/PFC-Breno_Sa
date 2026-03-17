"""
G2 — Impacto do bias por variável (versão melhorada)
Foco na história: VOLFLOW melhora consistentemente, MASSFLOW se divide
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

plt.rcParams.update({
    'font.family'      : 'DejaVu Sans',
    'figure.facecolor' : 'white',
    'axes.facecolor'   : 'white',
    'axes.spines.top'  : False,
    'axes.spines.right': False,
    'axes.spines.left' : False,
    'axes.spines.bottom': False,
    'axes.grid'        : True,
    'grid.color'       : '#F0F0F0',
    'grid.linewidth'   : 0.5,
    'xtick.color'      : '#888',
    'ytick.color'      : '#888',
    'xtick.labelsize'  : 8.5,
    'ytick.labelsize'  : 8.5,
})

AZUL    = '#2563EB'   # VOLFLOW
LARANJA = '#F97316'   # MASSFLOW
VERDE   = '#16A34A'
VERM    = '#DC2626'
CINZA   = '#9CA3AF'
PRETO   = '#111827'

ARQUIVO = r'C:\DigitalTwin\Backup\scripts\comparacao_bias_20260316_194336.xlsx'

# ── Carga ──────────────────────────────────────────────────────────────────────
xl = pd.ExcelFile(ARQUIVO)

df_var = xl.parse('🔬 Top Variáveis', header=None)
top_good = df_var.iloc[5:20,  [1,2,3,4,5]].copy()
top_bad  = df_var.iloc[24:39, [1,2,3,4,5]].copy()
for d, g in [(top_good,'melhorou'), (top_bad,'piorou')]:
    d.columns = ['Variável','MAE Sem','MAE Com','Var_abs','Var_pct']
    d.dropna(inplace=True)
    d['MAE Sem'] = pd.to_numeric(d['MAE Sem'])
    d['MAE Com'] = pd.to_numeric(d['MAE Com'])
    d['pct']     = (d['MAE Com'] - d['MAE Sem']) / d['MAE Sem'] * 100
    d['grupo']   = g

dv = pd.concat([top_good, top_bad]).reset_index(drop=True)

def tipo_var(n):
    if 'VOLFLOW'  in str(n): return 'VOLFLOW'
    if 'MASSFLOW' in str(n): return 'MASSFLOW'
    return 'Outro'

dv['tipo'] = dv['Variável'].apply(tipo_var)

# Abreviar nomes para leitura
def abrev(nome):
    nome = str(nome)
    nome = nome.replace('_MASSFLOW_MIXED', ' · MASSFLOW')
    nome = nome.replace('_MASSFLOW',       ' · MASSFLOW')
    nome = nome.replace('_VOLFLOW',        ' · VOLFLOW')
    nome = nome.replace('_RES',            '')
    nome = nome.replace('V-FLASH',         'FLASH')
    nome = nome.replace('V1-DEST',         'V1-DEST')
    return nome

dv['label'] = dv['Variável'].apply(abrev)
dv_s = dv.sort_values('pct').reset_index(drop=True)

cores_tipo = {'VOLFLOW': AZUL, 'MASSFLOW': LARANJA, 'Outro': CINZA}
cores_bar  = [VERDE if v < 0 else VERM for v in dv_s['pct']]

# ── Figura ─────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(11, 9), facecolor='white')
fig.suptitle('Impacto do bias no MAE por variável',
             fontsize=13, fontweight='bold', color=PRETO,
             x=0.04, ha='left', y=1.01)

y = np.arange(len(dv_s))

# Barras com opacidade por tipo
for i, (_, row) in enumerate(dv_s.iterrows()):
    cor_tipo = cores_tipo[row['tipo']]
    cor_dir  = VERDE if row['pct'] < 0 else VERM
    # Barra com cor de direção (verde/vermelho), borda da cor do tipo
    ax.barh(i, row['pct'],
            color=cor_dir, alpha=0.75,
            height=0.62, edgecolor=cor_tipo,
            linewidth=1.5, zorder=3)

# Linha zero
ax.axvline(0, color='#333', linewidth=1.2, zorder=4)

# Zona de separação melhorou/piorou
ax.axvspan(-6.5, 0,  alpha=0.03, color=VERDE, zorder=1)
ax.axvspan(0, 31,    alpha=0.03, color=VERM,  zorder=1)

# Labels dos valores
for i, (_, row) in enumerate(dv_s.iterrows()):
    v = row['pct']
    ha, off = ('right', -0.4) if v < 0 else ('left', 0.4)
    ax.text(v + off, i, f'{v:+.1f}%',
            va='center', ha=ha, fontsize=8,
            color=VERDE if v < 0 else VERM,
            fontweight='bold', zorder=5)

# Marcador de tipo no início da barra
for i, (_, row) in enumerate(dv_s.iterrows()):
    cor_tipo = cores_tipo[row['tipo']]
    ax.plot(0, i, 'o', color=cor_tipo, markersize=5,
            zorder=6, clip_on=False,
            markeredgecolor='white', markeredgewidth=0.5)

ax.set_yticks(y)
ax.set_yticklabels(dv_s['label'], fontsize=8.2, color='#333')
ax.set_xlabel('Variação % no MAE   (negativo = bias melhorou)', fontsize=9, color='#666')

# Rótulos de zona
ax.text(-6.2, len(dv_s) - 0.3, 'Melhorou', fontsize=8.5,
        color=VERDE, fontweight='bold', va='top', alpha=0.8)
ax.text(0.5,  len(dv_s) - 0.3, 'Piorou',   fontsize=8.5,
        color=VERM,  fontweight='bold', va='top', alpha=0.8)

# Linha divisória entre os dois grupos (entre última melhora e primeiro piora)
n_melh = (dv_s['pct'] < 0).sum()
ax.axhline(n_melh - 0.5, color='#CCCCCC', linewidth=1,
           linestyle='--', zorder=2)

# Legenda de tipo (círculos coloridos)
handles = [
    mpatches.Patch(color=AZUL,    label='VOLFLOW  —  fluxo volumétrico'),
    mpatches.Patch(color=LARANJA, label='MASSFLOW  —  fluxo mássico'),
]
leg = ax.legend(handles=handles, fontsize=8.5, frameon=True,
                framealpha=0.95, edgecolor='#E5E7EB',
                loc='lower right', labelcolor='#333',
                title='Tipo de variável', title_fontsize=8)
leg.get_title().set_color('#666')

# Anotação da conclusão
ax.text(0.99, 0.01,
        'VOLFLOW: melhora consistente  |  MASSFLOW: comportamento misto',
        transform=ax.transAxes, ha='right', va='bottom',
        fontsize=8, color='#666', style='italic')

ax.set_xlim(-7, 32)
plt.tight_layout()
plt.savefig('g2_variaveis_v2.png', dpi=160, bbox_inches='tight', facecolor='white')
plt.close()
print('✅  g2_variaveis_v2.png')