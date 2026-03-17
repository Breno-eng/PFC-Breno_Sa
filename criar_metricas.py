"""
================================================================================
MÉTRICAS DE QUALIDADE DE DADOS PARA MACHINE LEARNING
Análise ANTES do treinamento para identificar colunas problemáticas
================================================================================

Baseado em:
- "Garbage In, Garbage Out" (GIGO)
- Boas práticas de Data Quality para ML
- Paper: "Data Quality for Machine Learning Tasks" (Google Research)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import VarianceThreshold, mutual_info_regression
from sklearn.decomposition import PCA
import warnings
import yaml
from pathlib import Path
import os
import sys

warnings.filterwarnings('ignore')

# ==============================================================================
# CONFIGURAÇÃO (VIA YAML)
# ==============================================================================

# 1. Identificar a Raiz do Projeto
# Se o script está em: DigitalTwin/scripts/criar_metricas.py
# .parent = scripts
# .parent.parent = DigitalTwin (Raiz)
BASE_DIR = Path(__file__).resolve().parent.parent
print(f"📂 Raiz do Projeto: {BASE_DIR}")    

# 2. Carregar Configuração
config_path = BASE_DIR / "config" / "config.yaml"

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
except FileNotFoundError:
    print(f"❌ Erro: Config não encontrado em {config_path}")
    sys.exit(1)

# 3. Definir Caminhos
DATASET_PATH = BASE_DIR / cfg['paths']['dataset']
OUTPUT_PATH = BASE_DIR / cfg['paths']['output_metricas']

# Criar pasta de output se não existir
os.makedirs(OUTPUT_PATH, exist_ok=True)

# 4. Carregar Thresholds do YAML
# Se você ainda não atualizou o YAML, ele usa valores padrão para não quebrar
try:
    THRESHOLDS = cfg['data_quality']['thresholds']
    print("✅ Thresholds carregados do YAML")
except KeyError:
    print("⚠️  Aviso: Seção 'data_quality' não encontrada no YAML. Usando padrões.")
    THRESHOLDS = {
        'cv_minimo': 0.01, 'cv_muito_baixo': 0.05, 'variance_threshold': 0.01,
        'skewness_max': 5.0, 'kurtosis_max': 10.0, 'zeros_max': 0.80,
        'unique_values_min': 10, 'missing_max': 0.05, 'outliers_max': 0.10,
        'outliers_critical': 0.20, 'correlation_max': 0.95, 'vif_max': 10.0,
        'mutual_info_min': 0.01, 'max_value_concentration': 0.95
    }

print("="*80)
print("ANÁLISE DE QUALIDADE DE DADOS PARA MACHINE LEARNING")
print("="*80)
print(f"📂 Lendo dataset de: {DATASET_PATH}")
print(f"💾 Salvando resultados em: {OUTPUT_PATH}")

# ==============================================================================
# 1. CARREGAR E PREPARAR DADOS
# ==============================================================================

print("\n📂 Carregando dataset...")
df = pd.read_csv(DATASET_PATH)
print(f"✅ Dataset: {df.shape[0]:,} linhas × {df.shape[1]:,} colunas")

# Separar inputs e outputs
metadados = list(df.columns[0:3])
inputs = list(df.columns[3:22])
outputs_iniciais = list(df.columns[22:-2])

print(f"\n📊 Estrutura:")
print(f"   Inputs:  {len(inputs)}")
print(f"   Outputs: {len(outputs_iniciais)}")

# Focar apenas em outputs numéricos
outputs = [col for col in outputs_iniciais if df[col].dtype in ['int64', 'float64']]
print(f"   Outputs numéricos: {len(outputs)}")

# ==============================================================================
# 2. CRIAR DATAFRAME DE ANÁLISE
# ==============================================================================

print("\n" + "="*80)
print("CALCULANDO MÉTRICAS DE QUALIDADE")
print("="*80)

analise = []

for col in outputs:
    dados = df[col].dropna()
    
    if len(dados) == 0:
        continue
    
    # Estatísticas básicas
    mean = dados.mean()
    std = dados.std()
    
    # 1. VARIABILIDADE
    cv = std / (abs(mean) + 1e-10)
    variance = dados.var()
    value_range = dados.max() - dados.min()
    
    # 2. DISTRIBUIÇÃO
    skewness = stats.skew(dados) if len(dados) > 2 else 0
    kurtosis = stats.kurtosis(dados) if len(dados) > 2 else 0
    unique_values = dados.nunique()
    unique_ratio = unique_values / len(dados)
    
    # Porcentagem de zeros
    zeros_pct = (dados == 0).sum() / len(dados)
    
    # 3. QUALIDADE
    missing_pct = df[col].isna().sum() / len(df)
    
    # Outliers (IQR method)
    Q1, Q3 = np.percentile(dados, [25, 75])
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    outliers_pct = ((dados < lower_bound) | (dados > upper_bound)).sum() / len(dados)
    
    # 4. ESTABILIDADE (diferença entre percentis)
    p1, p99 = np.percentile(dados, [1, 99])
    percentile_range = p99 - p1
    outlier_ratio = percentile_range / (abs(mean) + 1e-10)
    
    # 5. INFORMAÇÃO
    # Entropia normalizada (0 a 1, onde 0 = sem informação)
    hist, _ = np.histogram(dados, bins=min(50, unique_values))
    hist = hist[hist > 0]
    probs = hist / hist.sum()
    entropy = -np.sum(probs * np.log2(probs)) if len(probs) > 0 else 0
    max_entropy = np.log2(len(probs)) if len(probs) > 0 else 1
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
    
    # 6. CONCENTRAÇÃO (Gini coefficient)
    # Mede quão concentrados estão os valores
    sorted_values = np.sort(np.abs(dados))
    n = len(sorted_values)
    index = np.arange(1, n + 1)
    gini = (2 * np.sum(index * sorted_values)) / (n * np.sum(sorted_values)) - (n + 1) / n
    
    value_counts = dados.value_counts()
    most_common_value = value_counts.index[0]
    most_common_count = value_counts.iloc[0]
    most_common_pct = value_counts.iloc[0] / len(dados)
    
    # SCORE DE QUALIDADE (0-100, quanto maior melhor)
    score_components = {
        'variabilidade': min(100, cv * 1000),  # Penaliza CV baixo
        'distribuicao': 100 - min(100, abs(skewness) * 10),  # Penaliza assimetria
        'informacao': normalized_entropy * 100,  # Premia alta entropia
        'qualidade': (1 - missing_pct - outliers_pct) * 100,  # Penaliza missing/outliers
        'diversidade': min(100, unique_ratio * 200),  # Premia mais valores únicos
    }
    
    quality_score = np.mean(list(score_components.values()))
    
    # IDENTIFICAR PROBLEMAS
    problemas = []
    severidade = 0
    problemas_distribuicao = 0

    # Concentração extrema em um único valor

    most_common_pct = dados.value_counts().iloc[0] / len(dados) if len(dados) > 0 else 0
    
    if most_common_pct > 0.95:  # 95% em um único valor
        problemas.append('VALOR_DOMINANTE_EXTREMO')
        severidade += 50
        
    # Variabilidade
    if cv < THRESHOLDS['cv_minimo']:
        problemas.append('CV_EXTREMAMENTE_BAIXO')
        severidade += 50
        
    elif cv < THRESHOLDS['cv_muito_baixo']:
        problemas.append('CV_MUITO_BAIXO')
        severidade += 30
    
    if variance < THRESHOLDS['variance_threshold']:
        problemas.append('VARIANCIA_BAIXA')
        severidade += 20
    
    if value_range / (abs(mean) + 1e-10) < 0.01:
        problemas.append('RANGE_PRATICAMENTE_ZERO')
        severidade += 40
        
    # Distribuição
    if abs(skewness) > THRESHOLDS['skewness_max']:
        problemas.append('DISTRIBUICAO_MUITO_ASSIMETRICA')
        severidade += 10
        problemas_distribuicao += 1
        
    if abs(kurtosis) > THRESHOLDS['kurtosis_max']:
        problemas.append('OUTLIERS_EXTREMOS')
        severidade += 15
        problemas_distribuicao += 1
        
    if zeros_pct > THRESHOLDS['zeros_max']:
        problemas.append('QUASE_TODOS_ZEROS')
        severidade += 40
    elif zeros_pct > 0.5:
        problemas.append('MAIORIA_ZEROS')
        severidade += 20
    
    if unique_values < THRESHOLDS['unique_values_min']:
        problemas.append('POUQUISSIMOS_VALORES')
        severidade += 25
    
    # Qualidade
    if missing_pct > THRESHOLDS['missing_max']:
        problemas.append('MUITOS_VALORES_FALTANTES')
        severidade += 30
    
    if outliers_pct > 0.20:  # > 20% = crítico
        problemas.append('OUTLIERS_CRITICOS')
        severidade += 30
        problemas_distribuicao += 1
        
    elif outliers_pct > THRESHOLDS['outliers_max']:  # > 10% = alto
        problemas.append('MUITOS_OUTLIERS')
        severidade += 15
        problemas_distribuicao += 1
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BÔNUS: Múltiplos problemas de distribuição
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if problemas_distribuicao >= 3:
        problemas.append('DISTRIBUICAO_MULTIPLOS_PROBLEMAS')
        severidade += 30
    
    # Informação
    if normalized_entropy < 0.3:
        problemas.append('BAIXA_ENTROPIA')
        severidade += 20
    
    if gini > 0.8:
        problemas.append('VALORES_MUITO_CONCENTRADOS')
        severidade += 15

    
    analise.append({
        'coluna': col,
        # Estatísticas básicas
        'mean': mean,
        'std': std,
        'min': dados.min(),
        'max': dados.max(),
        # Variabilidade
        'cv': cv,
        'variance': variance,
        'range': value_range,
        'outlier_ratio': outlier_ratio,
        # Distribuição
        'skewness': skewness,
        'kurtosis': kurtosis,
        'unique_values': unique_values,
        'unique_ratio': unique_ratio,
        'zeros_pct': zeros_pct,
        # Qualidade
        'missing_pct': missing_pct,
        'outliers_pct': outliers_pct,
        # Informação
        'entropy': normalized_entropy,
        'gini': gini,
        # Concentração (NOVO!) ← ADICIONAR ESTAS 3 LINHAS
        'most_common_value': most_common_value,        # ← NOVO
        'most_common_count': most_common_count,        # ← NOVO
        'most_common_pct': most_common_pct,            # ← NOVO
        # Scores
        'quality_score': quality_score,
        'severidade': severidade,
        'problemas': ', '.join(problemas) if problemas else 'OK',
        'n_problemas': len(problemas)
    })

# Criar DataFrame
df_analise = pd.DataFrame(analise)
df_analise = df_analise.sort_values('severidade', ascending=False)

print(f"\n✅ Análise completa de {len(df_analise)} colunas")

# ==============================================================================
# 3. ANÁLISE DE CORRELAÇÃO ENTRE OUTPUTS
# ==============================================================================
"""
print("\n" + "="*80)
print("ANÁLISE DE REDUNDÂNCIA (CORRELAÇÃO ENTRE OUTPUTS)")
print("="*80)

# Calcular matriz de correlação
df_outputs = df[outputs].copy()
corr_matrix = df_outputs.corr().abs()

# Encontrar pares altamente correlacionados
high_corr_pairs = []
for i in range(len(corr_matrix.columns)):
    for j in range(i+1, len(corr_matrix.columns)):
        if corr_matrix.iloc[i, j] > THRESHOLDS['correlation_max']:
            high_corr_pairs.append({
                'col1': corr_matrix.columns[i],
                'col2': corr_matrix.columns[j],
                'correlation': corr_matrix.iloc[i, j]
            })

df_high_corr = pd.DataFrame(high_corr_pairs)
print(f"\n🔍 Pares de outputs com correlação > {THRESHOLDS['correlation_max']}:")
print(f"   Total: {len(high_corr_pairs)} pares")

if len(high_corr_pairs) > 0:
    print(f"\n   Top 10 mais correlacionados:")
    for idx, row in df_high_corr.head(10).iterrows():
        print(f"   • {row['col1']:<40} ↔ {row['col2']:<40} (r={row['correlation']:.4f})")
"""
high_corr_pairs = []
df_high_corr = pd.DataFrame()
# ==============================================================================
# 4. ANÁLISE DE INFORMAÇÃO MÚTUA (se possível)
# ==============================================================================

print("\n" + "="*80)
print("ANÁLISE DE INFORMAÇÃO MÚTUA COM INPUTS")
print("="*80)

print("\n💡 Calculando informação mútua...")
print("   (Mede o quanto cada output depende dos inputs)")

# Preparar dados
X = df[inputs].dropna()
mi_scores = []

for output in outputs[:20]:  # Primeiros 20 para não demorar muito
    y = df.loc[X.index, output].dropna()
    X_clean = X.loc[y.index]
    
    try:
        mi = mutual_info_regression(X_clean, y, random_state=42)
        mi_score = mi.mean()
        mi_scores.append({
            'output': output,
            'mi_score': mi_score
        })
    except:
        pass

if len(mi_scores) > 0:
    df_mi = pd.DataFrame(mi_scores).sort_values('mi_score')
    
    print(f"\n📊 Outputs com MENOR informação mútua (primeiros 10):")
    print(f"   (Valores baixos = pouca relação com inputs)")
    for idx, row in df_mi.head(10).iterrows():
        print(f"   • {row['output']:<40} MI={row['mi_score']:.6f}")

# ==============================================================================
# 5. RELATÓRIO DE COLUNAS PROBLEMÁTICAS
# ==============================================================================

print("\n" + "="*80)
print("RELATÓRIO: COLUNAS RECOMENDADAS PARA REMOÇÃO")
print("="*80)

# Critérios de remoção
remover_severidade = df_analise[df_analise['severidade'] >= 50]
remover_cv = df_analise[df_analise['cv'] < THRESHOLDS['cv_muito_baixo']]
remover_zeros = df_analise[df_analise['zeros_pct'] > THRESHOLDS['zeros_max']]
remover_quality = df_analise[df_analise['quality_score'] < 30]

print(f"\n📋 CRITÉRIOS DE REMOÇÃO:")
print(f"   • Severidade ≥ 50:           {len(remover_severidade)} colunas")
print(f"   • CV < {THRESHOLDS['cv_muito_baixo']*100}%:                  {len(remover_cv)} colunas")
print(f"   • Zeros > {THRESHOLDS['zeros_max']*100}%:                {len(remover_zeros)} colunas")
print(f"   • Quality Score < 30:        {len(remover_quality)} colunas")

# União de todas as colunas problemáticas
colunas_remover = set(
    list(remover_severidade['coluna']) +
    list(remover_cv['coluna']) +
    list(remover_zeros['coluna']) +
    list(remover_quality['coluna'])
)

print(f"\n🎯 TOTAL DE COLUNAS PARA REMOVER: {len(colunas_remover)}")

# Top 30 piores
print(f"\n📉 TOP 30 COLUNAS COM PIOR QUALIDADE:")
print(f"\n{'#':<4} {'Coluna':<45} {'Sever.':<8} {'CV':<10} {'Quality':<10} {'Problemas'}")
print("-" * 130)

for idx, row in df_analise.head(30).iterrows():
    print(f"{idx+1:<4} {row['coluna']:<45} "
          f"{row['severidade']:<8.0f} "
          f"{row['cv']:<10.4f} "
          f"{row['quality_score']:<10.1f} "
          f"{row['problemas'][:60]}")

# ==============================================================================
# 6. VISUALIZAÇÕES
# ==============================================================================

print("\n" + "="*80)
print("GERANDO VISUALIZAÇÕES")
print("="*80)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 1: Distribuição de Quality Score
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig1, ax1 = plt.subplots(figsize=(10, 6))
ax1.hist(df_analise['quality_score'], bins=50, color='steelblue', alpha=0.7, edgecolor='black')
ax1.axvline(30, color='red', linestyle='--', linewidth=2, label='Limiar (30)')
ax1.set_xlabel('Quality Score', fontsize=12)
ax1.set_ylabel('Frequência', fontsize=12)
ax1.set_title('Distribuição de Quality Score', fontsize=14, fontweight='bold')
ax1.legend(fontsize=11)
ax1.grid(True, alpha=0.3)
caminho_fig1 = os.path.join(OUTPUT_PATH, '01_distribuicao_quality_score.png')
plt.savefig(caminho_fig1, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 01_distribuicao_quality_score.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 2: Distribuição de CV
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig2, ax2 = plt.subplots(figsize=(10, 6))
cv_plot = df_analise['cv'].clip(0, 1)  # Clipar para visualização
ax2.hist(cv_plot, bins=50, color='coral', alpha=0.7, edgecolor='black')
ax2.axvline(THRESHOLDS['cv_muito_baixo'], color='red', linestyle='--', linewidth=2, 
            label=f'Limiar ({THRESHOLDS["cv_muito_baixo"]})')
ax2.set_xlabel('Coeficiente de Variação (CV)', fontsize=12)
ax2.set_ylabel('Frequência', fontsize=12)
ax2.set_title('Distribuição de CV (Coeficiente de Variação)', fontsize=14, fontweight='bold')
ax2.legend(fontsize=11)
ax2.grid(True, alpha=0.3)
caminho_fig2 = os.path.join(OUTPUT_PATH, '02_distribuicao_cv.png')
plt.savefig(caminho_fig2, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 02_distribuicao_cv.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 3: Distribuição de Severidade
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig3, ax3 = plt.subplots(figsize=(10, 6))
ax3.hist(df_analise['severidade'], bins=30, color='indianred', alpha=0.7, edgecolor='black')
ax3.axvline(50, color='darkred', linestyle='--', linewidth=2, label='Limiar crítico (50)')
ax3.set_xlabel('Severidade', fontsize=12)
ax3.set_ylabel('Frequência', fontsize=12)
ax3.set_title('Distribuição de Severidade dos Problemas', fontsize=14, fontweight='bold')
ax3.legend(fontsize=11)
ax3.grid(True, alpha=0.3)
caminho_fig3 = os.path.join(OUTPUT_PATH, '03_distribuicao_severidade.png')
plt.savefig(caminho_fig3, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 03_distribuicao_severidade.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 4: CV vs Quality Score
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig4, ax4 = plt.subplots(figsize=(10, 6))
scatter = ax4.scatter(df_analise['cv'].clip(0, 1), df_analise['quality_score'], 
                     c=df_analise['severidade'], cmap='RdYlGn_r', alpha=0.6, s=50)
ax4.axvline(THRESHOLDS['cv_muito_baixo'], color='red', linestyle='--', alpha=0.5, linewidth=2)
ax4.axhline(30, color='red', linestyle='--', alpha=0.5, linewidth=2)
ax4.set_xlabel('CV (clipped at 1)', fontsize=12)
ax4.set_ylabel('Quality Score', fontsize=12)
ax4.set_title('CV vs Quality Score (cor = severidade)', fontsize=14, fontweight='bold')
cbar = plt.colorbar(scatter, ax=ax4, label='Severidade')
cbar.ax.tick_params(labelsize=10)
ax4.grid(True, alpha=0.3)
caminho_fig4 = os.path.join(OUTPUT_PATH, '04_cv_vs_quality_score.png')
plt.savefig(caminho_fig4, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 04_cv_vs_quality_score.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 5: Porcentagem de Zeros
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig5, ax5 = plt.subplots(figsize=(10, 6))
ax5.hist(df_analise['zeros_pct']*100, bins=30, color='purple', alpha=0.7, edgecolor='black')
ax5.axvline(THRESHOLDS['zeros_max']*100, color='red', linestyle='--', linewidth=2,
            label=f'Limiar ({THRESHOLDS["zeros_max"]*100}%)')
ax5.set_xlabel('% de Zeros', fontsize=12)
ax5.set_ylabel('Frequência', fontsize=12)
ax5.set_title('Distribuição de % de Zeros', fontsize=14, fontweight='bold')
ax5.legend(fontsize=11)
ax5.grid(True, alpha=0.3)
caminho_fig5 = os.path.join(OUTPUT_PATH, '05_distribuicao_zeros.png')
plt.savefig(caminho_fig5, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 05_distribuicao_zeros.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 6: Número de Problemas por Coluna
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig6, ax6 = plt.subplots(figsize=(10, 6))
problemas_count = df_analise['n_problemas'].value_counts().sort_index()
ax6.bar(problemas_count.index, problemas_count.values, color='tomato', alpha=0.7, edgecolor='black')
ax6.set_xlabel('Número de Problemas', fontsize=12)
ax6.set_ylabel('Quantidade de Colunas', fontsize=12)
ax6.set_title('Distribuição de Problemas por Coluna', fontsize=14, fontweight='bold')
ax6.grid(True, alpha=0.3, axis='y')
caminho_fig6 = os.path.join(OUTPUT_PATH, '06_problemas_por_coluna.png')
plt.savefig(caminho_fig6, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 06_problemas_por_coluna.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO 7: Top 30 Piores Colunas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig7, ax7 = plt.subplots(figsize=(14, 10))
top30 = df_analise.head(30).sort_values('severidade')
colors = ['red' if s >= 50 else 'orange' if s >= 30 else 'yellow' for s in top30['severidade']]
ax7.barh(range(len(top30)), top30['severidade'], color=colors, alpha=0.7, edgecolor='black')
ax7.set_yticks(range(len(top30)))
ax7.set_yticklabels([col[:50] for col in top30['coluna']], fontsize=9)
ax7.set_xlabel('Severidade', fontsize=12)
ax7.set_title('Top 30 Colunas com Maior Severidade', fontsize=14, fontweight='bold')
ax7.axvline(50, color='darkred', linestyle='--', linewidth=2, label='Crítico (≥50)')
ax7.axvline(30, color='orange', linestyle='--', linewidth=2, label='Alto (≥30)')
ax7.legend(fontsize=11)
ax7.grid(True, alpha=0.3, axis='x')
caminho_fig7 = os.path.join(OUTPUT_PATH, '07_top30_piores_colunas.png')
plt.savefig(caminho_fig7, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 07_top30_piores_colunas.png")
plt.close()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GRÁFICO COMPLETO: Dashboard com Todos os Gráficos
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n📊 Gerando dashboard completo...")

fig = plt.figure(figsize=(20, 12))
gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

# 1. Distribuição de Quality Score
ax1 = fig.add_subplot(gs[0, 0])
ax1.hist(df_analise['quality_score'], bins=50, color='steelblue', alpha=0.7, edgecolor='black')
ax1.axvline(30, color='red', linestyle='--', label='Limiar (30)')
ax1.set_xlabel('Quality Score')
ax1.set_ylabel('Frequência')
ax1.set_title('Distribuição de Quality Score')
ax1.legend()
ax1.grid(True, alpha=0.3)

# 2. Distribuição de CV
ax2 = fig.add_subplot(gs[0, 1])
cv_plot = df_analise['cv'].clip(0, 1)
ax2.hist(cv_plot, bins=50, color='coral', alpha=0.7, edgecolor='black')
ax2.axvline(THRESHOLDS['cv_muito_baixo'], color='red', linestyle='--', 
            label=f'Limiar ({THRESHOLDS["cv_muito_baixo"]})')
ax2.set_xlabel('Coeficiente de Variação (CV)')
ax2.set_ylabel('Frequência')
ax2.set_title('Distribuição de CV')
ax2.legend()
ax2.grid(True, alpha=0.3)

# 3. Distribuição de Severidade
ax3 = fig.add_subplot(gs[0, 2])
ax3.hist(df_analise['severidade'], bins=30, color='indianred', alpha=0.7, edgecolor='black')
ax3.axvline(50, color='darkred', linestyle='--', linewidth=2, label='Limiar crítico (50)')
ax3.set_xlabel('Severidade')
ax3.set_ylabel('Frequência')
ax3.set_title('Distribuição de Severidade dos Problemas')
ax3.legend()
ax3.grid(True, alpha=0.3)

# 4. CV vs Quality Score
ax4 = fig.add_subplot(gs[1, 0])
scatter = ax4.scatter(df_analise['cv'].clip(0, 1), df_analise['quality_score'], 
                     c=df_analise['severidade'], cmap='RdYlGn_r', alpha=0.6, s=50)
ax4.axvline(THRESHOLDS['cv_muito_baixo'], color='red', linestyle='--', alpha=0.5)
ax4.axhline(30, color='red', linestyle='--', alpha=0.5)
ax4.set_xlabel('CV (clipped at 1)')
ax4.set_ylabel('Quality Score')
ax4.set_title('CV vs Quality Score (cor = severidade)')
plt.colorbar(scatter, ax=ax4, label='Severidade')
ax4.grid(True, alpha=0.3)

# 5. Porcentagem de zeros
ax5 = fig.add_subplot(gs[1, 1])
ax5.hist(df_analise['zeros_pct']*100, bins=30, color='purple', alpha=0.7, edgecolor='black')
ax5.axvline(THRESHOLDS['zeros_max']*100, color='red', linestyle='--', 
            label=f'Limiar ({THRESHOLDS["zeros_max"]*100}%)')
ax5.set_xlabel('% de Zeros')
ax5.set_ylabel('Frequência')
ax5.set_title('Distribuição de % de Zeros')
ax5.legend()
ax5.grid(True, alpha=0.3)

# 6. Número de problemas por coluna
ax6 = fig.add_subplot(gs[1, 2])
problemas_count = df_analise['n_problemas'].value_counts().sort_index()
ax6.bar(problemas_count.index, problemas_count.values, color='tomato', alpha=0.7, edgecolor='black')
ax6.set_xlabel('Número de Problemas')
ax6.set_ylabel('Quantidade de Colunas')
ax6.set_title('Distribuição de Problemas por Coluna')
ax6.grid(True, alpha=0.3, axis='y')

# 7. Top 20 piores (barras horizontais)
ax7 = fig.add_subplot(gs[2, :])
top20 = df_analise.head(20).sort_values('severidade')
colors = ['red' if s >= 50 else 'orange' if s >= 30 else 'yellow' for s in top20['severidade']]
ax7.barh(range(len(top20)), top20['severidade'], color=colors, alpha=0.7, edgecolor='black')
ax7.set_yticks(range(len(top20)))
ax7.set_yticklabels([col[:40] for col in top20['coluna']], fontsize=8)
ax7.set_xlabel('Severidade')
ax7.set_title('Top 20 Colunas com Maior Severidade')
ax7.axvline(50, color='darkred', linestyle='--', linewidth=2, label='Crítico')
ax7.axvline(30, color='orange', linestyle='--', linewidth=2, label='Alto')
ax7.legend()
ax7.grid(True, alpha=0.3, axis='x')

plt.suptitle('Análise de Qualidade de Dados - Métricas Pré-Treinamento', 
             fontsize=16, fontweight='bold', y=0.995)

caminho_completo = os.path.join(OUTPUT_PATH, '00_DASHBOARD_COMPLETO.png')
plt.savefig(caminho_completo, dpi=150, bbox_inches='tight')
print(f"✅ Salvo: 00_DASHBOARD_COMPLETO.png")
plt.show()
plt.close()

print("\n" + "="*80)
print("✅ TODAS AS VISUALIZAÇÕES FORAM GERADAS!")
print("="*80)

# ==============================================================================
# 7. EXPORTAR RESULTADOS
# ==============================================================================

print("\n" + "="*80)
print("EXPORTANDO RESULTADOS")
print("="*80)

# Salvar análise completa
caminho_analise = os.path.join(OUTPUT_PATH, 'analise_qualidade_completa.csv')
df_analise.to_csv(caminho_analise, index=False)
print(f"✅ Salvo: {caminho_analise}")

# Salvar lista de colunas para remover
caminho_remover = os.path.join(OUTPUT_PATH, 'colunas_recomendadas_remover.csv')
df_remover = df_analise[df_analise['coluna'].isin(colunas_remover)].copy()
df_remover.to_csv(caminho_remover, index=False)
print(f"✅ Salvo: {caminho_remover}")

# Salvar correlações altas
if len(high_corr_pairs) > 0:
    caminho_corr = os.path.join(OUTPUT_PATH, 'outputs_alta_correlacao.csv')
    df_high_corr.to_csv(caminho_corr, index=False)
    print(f"✅ Salvo: {caminho_corr}")

# ==============================================================================
# 8. CÓDIGO PARA APLICAR NO TREINAMENTO
# ==============================================================================

print("\n" + "="*80)
print("CÓDIGO PARA APLICAR NO SEU SCRIPT DE TREINAMENTO")
print("="*80)

print(f"""
# Lista de {len(colunas_remover)} colunas recomendadas para REMOÇÃO:
colunas_remover = {sorted(list(colunas_remover))}

# Aplicar filtro ANTES do treinamento:
outputs_detectados = [col for col in outputs_detectados 
                      if col not in colunas_remover]

# Ou remover do DataFrame:
df_limpo = df.drop(columns=colunas_remover, errors='ignore')

print(f"Colunas removidas: {{len(colunas_remover)}}")
print(f"Colunas restantes: {{len(outputs_detectados)}}")
""")

# ==============================================================================
# 9. RESUMO EXECUTIVO
# ==============================================================================

print("\n" + "="*80)
print("RESUMO EXECUTIVO")
print("="*80)

print(f"""
📊 ANÁLISE DE {len(df_analise)} OUTPUTS:

🔍 MÉTRICAS CALCULADAS:
   1. Variabilidade: CV, Variância, Range
   2. Distribuição: Skewness, Kurtosis, % Zeros, Valores únicos
   3. Qualidade: Missing values, Outliers
   4. Informação: Entropia, Gini coefficient
   5. Correlação: Entre outputs (redundância)
   6. Concentração: % do valor dominante

📈 ESTATÍSTICAS GERAIS:
   • Quality Score médio: {df_analise['quality_score'].mean():.1f}/100
   • CV médio: {df_analise['cv'].mean():.4f}
   • Severidade média: {df_analise['severidade'].mean():.1f}/100
   • % média de zeros: {df_analise['zeros_pct'].mean()*100:.1f}%

⚠️  PROBLEMAS IDENTIFICADOS:
   • Colunas com severidade ≥ 50: {len(remover_severidade)}
   • Colunas com CV < 5%: {len(remover_cv)}
   • Colunas com >80% zeros: {len(remover_zeros)}
   • Colunas com quality < 30: {len(remover_quality)}

🎯 RECOMENDAÇÃO:
   REMOVER {len(colunas_remover)} colunas ANTES do treinamento!
   
   Estas colunas têm baixa qualidade e não contribuirão significativamente
   para o aprendizado do modelo. Removê-las irá:
   • ✅ Reduzir tempo de treinamento
   • ✅ Diminuir uso de memória
   • ✅ Evitar overfitting
   • ✅ Melhorar generalização
   • ✅ Simplificar o modelo

📁 ARQUIVOS GERADOS:
   • analise_qualidade_completa.csv
   • colunas_recomendadas_remover.csv
   • outputs_alta_correlacao.csv (se houver)
   • analise_qualidade_dados_pre_treinamento.png
""")

print("\n" + "="*80)
print("✅ ANÁLISE COMPLETA FINALIZADA!")
print("="*80)