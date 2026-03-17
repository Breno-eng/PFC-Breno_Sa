import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
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
    'xtick.color'      : '#AAA',
    'ytick.color'      : '#AAA',
    'xtick.labelsize'  : 8,
    'ytick.labelsize'  : 8,
})

PRETO   = '#111827'
AZUL    = '#2563EB'
LARANJA = '#F97316'
VERDE   = '#16A34A'
VERM    = '#DC2626'
CINZA   = '#6B7280'

ARQUIVO = r'C:\DigitalTwin\Backup\scripts\comparacao_bias_20260316_194336.xlsx'

# ── Carga ──────────────────────────────────────────────────────────────────────
xl = pd.ExcelFile(ARQUIVO)
df_raw = xl.parse('📋 Dados Target', header=None)
hr = df_raw[df_raw.apply(lambda r: 'Caso' in r.values, axis=1)].index[0]
df = xl.parse('📋 Dados Target', header=None, skiprows=hr+1)
df.columns = df_raw.iloc[hr].values
df.columns = [str(c) for c in df.columns]
df = df.dropna(how='all')
df = df[df['Caso'].apply(lambda x: str(x).replace('.0','').isdigit())]
df['Caso'] = df['Caso'].astype(float).astype(int)
for col in ['Keras Sem', 'Keras Com', 'Aspen']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df.dropna(subset=['Keras Sem', 'Keras Com', 'Aspen'])
df = df.sort_values('Aspen').reset_index(drop=True)

bins   = [-0.001, 0.15, 0.46, 0.90, 1.001]
labels = ['< 0.15', '0.15 – 0.46', '0.46 – 0.90', '≥ 0.90']
df['faixa'] = pd.cut(df['Aspen'], bins=bins, labels=labels)


# ══════════════════════════════════════════════════════════════════════════════
# FIGURA 1 — Scorecard de métricas (tabela 4.5)
# ══════════════════════════════════════════════════════════════════════════════

metricas_target = [
    # (label,               sem,       com,      unidade, menor_melhor)
    ('Alarmes disparados',  231,       229,       '',      True),
    ('Falsos alarmes',       26,        25,       '',      True),
    ('Taxa falso alarme',  11.26,     10.92,      '%',     True),
    ('MAE — var. crítica',  0.02721,   0.02892,   '',      True),
    ('SMAPE — var. crítica',3.77,      3.86,      '%',     True),
]

metricas_global = [
    ('MAE global',          83.15,     81.91,     '',      True),
    ('SMAPE global',        11.375,    11.381,    '%',     True),
]

def cor_metrica(sem, com, menor_melhor):
    if sem == com: return CINZA
    melhorou = (com < sem) if menor_melhor else (com > sem)
    return VERDE if melhorou else VERM

fig = plt.figure(figsize=(14, 5), facecolor='white')
fig.suptitle('Resumo comparativo — Com Bias vs Sem Bias',
             fontsize=12, fontweight='bold', color=PRETO,
             x=0.04, ha='left', y=1.03)

gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.12,
                       left=0.03, right=0.97, top=0.88, bottom=0.08)

def draw_scorecard(ax, titulo, metricas, subtitulo=''):
    ax.set_facecolor('white')
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # Cabeçalho da seção
    ax.text(0.02, 0.97, titulo, fontsize=10, fontweight='bold',
            color=PRETO, va='top', transform=ax.transAxes)
    if subtitulo:
        ax.text(0.02, 0.90, subtitulo, fontsize=7.5, color=CINZA,
                va='top', transform=ax.transAxes, style='italic')

    # Cabeçalho das colunas
    y_header = 0.82
    for xpos, txt, ha in [
        (0.38, 'Sem Bias', 'center'),
        (0.60, 'Com Bias', 'center'),
        (0.82, 'Variação', 'center'),
        (0.97, '',         'right'),
    ]:
        ax.text(xpos, y_header, txt, fontsize=8, color=CINZA,
                ha=ha, va='top', transform=ax.transAxes, fontweight='bold')

    # Linha separadora
    ax.plot([0.01, 0.98], [y_header - 0.04, y_header - 0.04],
            color='#E5E7EB', linewidth=0.8, transform=ax.transAxes,
            clip_on=False)

    n = len(metricas)
    row_h = 0.72 / n

    for i, (label, sem, com, unid, menor_melhor) in enumerate(metricas):
        y = (y_header - 0.08) - i * row_h
        cor = cor_metrica(sem, com, menor_melhor)

        # Fundo alternado suave
        if i % 2 == 0:
            rect = mpatches.FancyBboxPatch(
                (0.01, y - row_h * 0.45), 0.97, row_h * 0.9,
                boxstyle='round,pad=0.005',
                facecolor='#F9FAFB', edgecolor='none',
                transform=ax.transAxes, clip_on=False)
            ax.add_patch(rect)

        # Label
        ax.text(0.03, y, label, fontsize=8.5, color='#374151',
                va='center', transform=ax.transAxes)

        # Sem Bias
        fmt_sem = f'{sem:.4f}' if isinstance(sem, float) and sem < 10 else f'{sem:.2f}'
        ax.text(0.38, y, f'{fmt_sem}{unid}', fontsize=8.5, color=AZUL,
                ha='center', va='center', transform=ax.transAxes, fontweight='bold')

        # Com Bias
        fmt_com = f'{com:.4f}' if isinstance(com, float) and com < 10 else f'{com:.2f}'
        ax.text(0.60, y, f'{fmt_com}{unid}', fontsize=8.5, color=LARANJA,
                ha='center', va='center', transform=ax.transAxes, fontweight='bold')

        # Variação %
        if sem != 0 and sem != com:
            var = (com - sem) / sem * 100
            sinal = '▼' if var < 0 else '▲'
            ax.text(0.82, y, f'{sinal} {abs(var):.1f}%', fontsize=8.5,
                    color=cor, ha='center', va='center',
                    transform=ax.transAxes, fontweight='bold')
        else:
            ax.text(0.82, y, '—', fontsize=8.5, color=CINZA,
                    ha='center', va='center', transform=ax.transAxes)

        # Ícone
        icon = '✓' if cor == VERDE else ('✗' if cor == VERM else '—')
        ax.text(0.96, y, icon, fontsize=10, color=cor,
                ha='center', va='center', transform=ax.transAxes, fontweight='bold')

ax1 = fig.add_subplot(gs[0, 0])
draw_scorecard(ax1, 'Variável crítica',
               metricas_target,
               'PRODUTO_ACETA-01_MOLEFRAC_MIXED  |  limite 0.90')

ax2 = fig.add_subplot(gs[0, 1])
draw_scorecard(ax2, 'Métricas globais',
               metricas_global,
               'Todas as 255 variáveis')

# Legenda de cores
fig.text(0.04, 0.01,
         '● Azul = Sem Bias   ● Laranja = Com Bias   '
         '▼ Verde = melhora   ▲ Vermelho = piora',
         fontsize=7.5, color=CINZA)

plt.savefig('g0_scorecard.png', dpi=160, bbox_inches='tight', facecolor='white')
plt.close()
print('✅  g0_scorecard.png')


# ══════════════════════════════════════════════════════════════════════════════
# FIGURA 2 — Quem acerta mais (4×2, igual à v2)
# ══════════════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(4, 2, figsize=(14, 14), facecolor='white')
fig.suptitle('Quem acerta mais? — Aspen real vs predições',
             fontsize=13, fontweight='bold', color=PRETO, y=1.005, x=0.04, ha='left')

for row, faixa in enumerate(labels):
    sub = df[df['faixa'] == faixa].reset_index(drop=True)
    xi  = np.arange(len(sub))
    n   = len(sub)

    mae_sem = (sub['Keras Sem'] - sub['Aspen']).abs().mean()
    mae_com = (sub['Keras Com'] - sub['Aspen']).abs().mean()
    melhor  = 'Sem Bias' if mae_sem < mae_com else 'Com Bias'
    cor_m   = AZUL if mae_sem < mae_com else LARANJA
    diff    = abs(mae_com - mae_sem) / mae_sem * 100

    y_min = min(sub['Aspen'].quantile(0.01),
                sub['Keras Sem'].quantile(0.01),
                sub['Keras Com'].quantile(0.01)) - 0.02
    y_max = max(sub['Aspen'].quantile(0.99),
                sub['Keras Sem'].quantile(0.99),
                sub['Keras Com'].quantile(0.99)) + 0.02
    y_min = max(y_min, 0)
    y_max = min(y_max, 1.05)

    for col_idx, (col_erro, cor, titulo_col) in enumerate([
        ('Keras Sem', AZUL,    'Sem Bias'),
        ('Keras Com', LARANJA, 'Com Bias'),
    ]):
        ax = axes[row, col_idx]

        ax.fill_between(xi,
                        sub['Aspen'].clip(y_min, y_max),
                        sub[col_erro].clip(y_min, y_max),
                        alpha=0.15, color=cor, zorder=1)

        ax.plot(xi, sub[col_erro].clip(y_min, y_max),
                color=cor, linewidth=1.3, alpha=0.85, zorder=3, label=titulo_col)

        ax.plot(xi, sub['Aspen'].clip(y_min, y_max),
                color=PRETO, linewidth=2, zorder=4, label='Aspen real')

        ax.set_ylim(y_min, y_max)
        ax.set_xlim(0, len(sub) - 1)

        if row == 0:
            ax.set_title(titulo_col, fontsize=11, fontweight='bold',
                         color=cor, pad=10)

        if col_idx == 0:
            ax.set_ylabel(faixa, fontsize=10, fontweight='bold',
                          color='#444', labelpad=10)

        if row == 3:
            ax.set_xlabel(f'casos ordenados pelo Aspen  (n={n})',
                          fontsize=8, color='#AAA')
        else:
            ax.set_xticklabels([])

        ax.text(0.98, 0.96,
                f'MAE = {(sub[col_erro] - sub["Aspen"]).abs().mean():.4f}',
                transform=ax.transAxes, ha='right', va='top',
                fontsize=8.5, color=cor, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                          edgecolor='#E5E7EB', linewidth=0.7))

        if col_idx == 0:
            ax.legend(fontsize=8, frameon=False, loc='upper left',
                      labelcolor='#333', handlelength=1.2, handletextpad=0.4)

    axes[row, 1].text(1.05, 0.5,
                      f'✦  {melhor}\n{diff:.1f}% melhor',
                      transform=axes[row, 1].transAxes,
                      ha='left', va='center', fontsize=8.5,
                      fontweight='bold', color=cor_m)

plt.tight_layout(h_pad=1.5, w_pad=1.0)
plt.savefig('g_quem_acerta_v2.png', dpi=160, bbox_inches='tight', facecolor='white')
plt.close()
print('✅  g_quem_acerta_v2.png')