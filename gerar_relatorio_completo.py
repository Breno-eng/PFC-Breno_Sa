import pandas as pd
import json
import numpy as np
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📂 CAMINHOS DOS ARQUIVOS (ajuste se necessário)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BASE_DIR = Path(r"C:\DigitalTwin")

# Arquivos principais
CONFIG_JSON = BASE_DIR / "Modelos Keras" / "config_final.json"
R2_CSV = BASE_DIR / "Modelos Keras" / "r2_individual_por_output.csv"
FILTRO_CSV = BASE_DIR / "metricas" / "colunas_recomendadas_remover.csv"
DATASET_CSV = BASE_DIR / "datasets_gerados" / "dataset_unificado.csv"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📊 CARREGAR DADOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("="*80)
print("📊 RELATÓRIO COMPLETO DE RESULTADOS DO TCC")
print("="*80)

# 1. CONFIG FINAL (JSON)
with open(CONFIG_JSON, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 2. R² POR OUTPUT (CSV)
df_r2 = pd.read_csv(R2_CSV)

# 3. FILTRO DE QUALIDADE (CSV)
try:
    df_filtro = pd.read_csv(FILTRO_CSV)
    tem_filtro = True
except:
    df_filtro = None
    tem_filtro = False

# 4. DATASET ORIGINAL (CSV) - só para contar linhas
df_dataset = pd.read_csv(DATASET_CSV)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 1: DATASET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("1️⃣ DATASET")
print("="*80)

print(f"Total de linhas no CSV original: {len(df_dataset):,}")
print(f"Total de colunas originais: {len(df_dataset.columns):,}")
print(f"Linhas após limpeza: {config['dataset']['total_linhas']:,}")

divisao = config['dataset']['divisao']
print(f"\n📊 Divisão dos dados:")
print(f"   Treino:     {divisao['treino']:,} ({divisao['treino']/config['dataset']['total_linhas']*100:.1f}%)")
print(f"   Validação:  {divisao['validacao']:,} ({divisao['validacao']/config['dataset']['total_linhas']*100:.1f}%)")
print(f"   Teste:      {divisao['teste']:,} ({divisao['teste']/config['dataset']['total_linhas']*100:.1f}%)")

if 'fonte_dados' in df_dataset.columns:
    print(f"\n📂 Distribuição por fonte de dados:")
    fontes = df_dataset['fonte_dados'].value_counts()
    for fonte, count in fontes.items():
        print(f"   • {fonte}: {count:,} ({count/len(df_dataset)*100:.1f}%)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 2: FILTRO DE QUALIDADE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("2️⃣ FILTRO DE QUALIDADE")
print("="*80)

if tem_filtro:
    print(f"Colunas sugeridas para remoção: {len(df_filtro)}")
    print(f"\nTop 5 piores outputs (recomendados para remoção):")
    print(df_filtro.head()[['coluna', 'quality_score', 'severidade', 'cv', 'zeros_pct']].to_string(index=False))
else:
    print("⚠️ Arquivo de filtro não encontrado")

outputs_removidos = config['outputs_removidos']
print(f"\n🗑️ Outputs efetivamente removidos:")
print(f"   Total: {outputs_removidos['total']}")
print(f"   Critério: {outputs_removidos['criterio']}")

if outputs_removidos['total'] > 0 and len(outputs_removidos['lista']) > 0:
    print(f"\n   Primeiros 5 removidos:")
    for i, nome in enumerate(outputs_removidos['lista'][:5], 1):
        print(f"   {i}. {nome}")
    if len(outputs_removidos['lista']) > 5:
        print(f"   ... e mais {len(outputs_removidos['lista'])-5}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 3: MODELO BASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("3️⃣ MODELO BASE")
print("="*80)

modelo_info = config['modelo']
resultados = config['resultados_globais']

print(f"Arquitetura: {modelo_info['tipo']}")
print(f"Parâmetros totais: {modelo_info['parametros_total']:,}")
print(f"Épocas treinadas: {modelo_info['epocas_treinadas']}")
print(f"Batch size: {modelo_info['batch_size']}")
print(f"Learning rate inicial: {modelo_info['learning_rate_inicial']}")
print(f"Otimizador: {modelo_info['optimizer']}")

print(f"\n📊 Desempenho no conjunto de teste:")
print(f"   R² médio:    {resultados['r2_medio']:.4f}")
print(f"   R² mediano:  {resultados['r2_mediano']:.4f}")
print(f"   R² mínimo:   {resultados['r2_minimo']:.4f}")
print(f"   R² máximo:   {resultados['r2_maximo']:.4f}")
print(f"   RMSE médio:  {resultados['rmse_medio']:.4f}")
print(f"   MAE médio:   {resultados['mae_medio']:.4f}")
print(f"   SMAPE médio: {resultados['smape_medio']:.2f}%")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 4: VARIÁVEL CRÍTICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("4️⃣ VARIÁVEL CRÍTICA: PRODUTO_ACETA-01_MOLEFRAC_MIXED")
print("="*80)

# Buscar no historico de retreinamentos
historico = config['retreinamentos']['historico']
critica_info = None

for retreino in historico:
    if retreino['output'] == 'PRODUTO_ACETA-01_MOLEFRAC_MIXED':
        critica_info = retreino
        break

if critica_info:
    print(f"R² inicial (modelo base):  {critica_info['r2_inicial']:.4f}")
    print(f"R² final (especialista):   {critica_info['r2_final']:.4f}")
    print(f"Melhoria:                  +{critica_info['melhoria']:.4f}")
    print(f"Tentativas de retreino:    {critica_info['tentativas']}")
    print(f"Atingiu alvo (R²≥0.95):    {'✅ SIM' if critica_info['atingiu_alvo'] else '❌ NÃO'}")
    print(f"Atingiu R²≥0.98:           {'✅ SIM' if critica_info.get('atingiu_98', False) else '❌ NÃO'}")
    
    status = "✅ APROVADO" if critica_info['atingiu_alvo'] else "❌ REPROVADO"
    print(f"\n{'='*40}")
    print(f"STATUS FINAL: {status}")
    print(f"{'='*40}")
else:
    # Buscar no df_r2 caso não tenha sido retreinada
    linha = df_r2[df_r2['output'] == 'PRODUTO_ACETA-01_MOLEFRAC_MIXED']
    if not linha.empty:
        r2_final = linha.iloc[0]['r2']
        print(f"R² final: {r2_final:.4f}")
        print(f"Status: {'✅ APROVADO' if r2_final >= 0.95 else '❌ REPROVADO'}")
        print(f"Tem especialista: {'SIM' if linha.iloc[0]['tem_especialista'] else 'NÃO'}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 5: SISTEMA DE ESPECIALISTAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("5️⃣ SISTEMA DE ESPECIALISTAS")
print("="*80)

retreinos_info = config['retreinamentos']

print(f"Outputs retreinados:       {retreinos_info['total_outputs_retreinados']}")
print(f"Melhoria média de R²:      +{retreinos_info['melhoria_media']:.4f}")
print(f"Alvos atingidos:           {retreinos_info['alvos_atingidos']} / {retreinos_info['total_outputs_retreinados']}")

if retreinos_info['total_outputs_retreinados'] > 0:
    taxa_sucesso = retreinos_info['alvos_atingidos'] / retreinos_info['total_outputs_retreinados'] * 100
    print(f"Taxa de sucesso:           {taxa_sucesso:.1f}%")
    
    # Top 5 maiores melhorias
    melhorias = sorted(historico, key=lambda x: x['melhoria'], reverse=True)
    print(f"\n🏆 Top 5 maiores melhorias:")
    for i, ret in enumerate(melhorias[:5], 1):
        print(f"   {i}. {ret['output'][:50]:<50} | R²: {ret['r2_inicial']:.4f} → {ret['r2_final']:.4f} (+{ret['melhoria']:.4f})")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 6: APROVAÇÃO FINAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("6️⃣ APROVAÇÃO FINAL")
print("="*80)

aprovacao = config['aprovacao']

print(f"\n🔴 VARIÁVEIS CRÍTICAS (R² ≥ 0.95):")
print(f"   Total:     {aprovacao['criticas']['total']}")
print(f"   Aprovadas: {aprovacao['criticas']['aprovadas']}")
print(f"   Taxa:      {aprovacao['criticas']['taxa_pct']:.1f}%")

print(f"\n🟡 VARIÁVEIS NORMAIS (R² ≥ 0.90):")
print(f"   Total:     {aprovacao['normais']['total']}")
print(f"   Aprovadas: {aprovacao['normais']['aprovadas']}")
print(f"   Taxa:      {aprovacao['normais']['taxa_pct']:.1f}%")

print(f"\n📊 GERAL:")
print(f"   Total:     {aprovacao['geral']['total']}")
print(f"   Aprovadas: {aprovacao['geral']['aprovadas']}")
print(f"   Taxa:      {aprovacao['geral']['taxa_pct']:.1f}%")
print(f"   Meta:      90%")
print(f"   Status:    {'✅ META ATINGIDA' if aprovacao['geral']['meta_atingida'] else '❌ META NÃO ATINGIDA'}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 7: TOP 10 MELHORES E PIORES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("7️⃣ ANÁLISE INDIVIDUAL DOS OUTPUTS")
print("="*80)

print(f"\n🏆 TOP 10 MELHORES OUTPUTS:")
top10_melhores = df_r2.sort_values('r2', ascending=False).head(10)
for i, (idx, row) in enumerate(top10_melhores.iterrows(), 1):
    especialista = "✓" if row['tem_especialista'] else ""
    critica = "🔴" if row['critica'] else ""
    print(f"   {i:2d}. {row['output'][:50]:<50} | R²={row['r2']:.4f} {critica} {especialista}")

print(f"\n📉 TOP 10 PIORES OUTPUTS:")
top10_piores = df_r2.sort_values('r2', ascending=True).head(10)
for i, (idx, row) in enumerate(top10_piores.iterrows(), 1):
    especialista = "✓" if row['tem_especialista'] else ""
    critica = "🔴" if row['critica'] else ""
    aprovado = "✅" if row['aprovado'] else "❌"
    print(f"   {i:2d}. {row['output'][:50]:<50} | R²={row['r2']:.4f} {aprovado} {critica} {especialista}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 8: ESTATÍSTICAS ADICIONAIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("8️⃣ ESTATÍSTICAS ADICIONAIS")
print("="*80)

# Distribuição de R²
print(f"\n📊 Distribuição de R²:")
bins = [0.0, 0.70, 0.80, 0.90, 0.95, 0.98, 1.0]
labels = ['<0.70', '0.70-0.80', '0.80-0.90', '0.90-0.95', '0.95-0.98', '≥0.98']
df_r2['faixa_r2'] = pd.cut(df_r2['r2'], bins=bins, labels=labels, include_lowest=True)
dist = df_r2['faixa_r2'].value_counts().sort_index()

for faixa, count in dist.items():
    pct = count / len(df_r2) * 100
    barra = "█" * int(pct / 2)
    print(f"   {faixa:>10} | {count:3d} ({pct:5.1f}%) {barra}")

# Especialistas vs Base
total_com_especialista = df_r2['tem_especialista'].sum()
print(f"\n🔧 Uso de especialistas:")
print(f"   Outputs com especialista: {total_com_especialista} / {len(df_r2)} ({total_com_especialista/len(df_r2)*100:.1f}%)")
print(f"   Outputs só com base:      {len(df_r2) - total_com_especialista} / {len(df_r2)} ({(len(df_r2)-total_com_especialista)/len(df_r2)*100:.1f}%)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 SEÇÃO 9: RESUMO EXECUTIVO PARA O TCC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print(f"\n{'='*80}")
print("📋 RESUMO EXECUTIVO PARA O TCC")
print("="*80)

print(f"""
Dataset:
  • {len(df_dataset):,} simulações geradas
  • {config['dataset']['total_linhas']:,} casos válidos após limpeza
  • {config['modelo']['n_inputs']} variáveis de entrada
  • {config['modelo']['n_outputs']} variáveis de saída (após filtro)

Modelo:
  • Arquitetura: {modelo_info['tipo']}
  • {modelo_info['parametros_total']:,} parâmetros treináveis
  • {modelo_info['epocas_treinadas']} épocas de treinamento
  • R² médio: {resultados['r2_medio']:.4f}

Sistema de Especialistas:
  • {retreinos_info['total_outputs_retreinados']} outputs retreinados
  • Melhoria média: +{retreinos_info['melhoria_media']:.4f}
  • Taxa de sucesso: {retreinos_info['alvos_atingidos']}/{retreinos_info['total_outputs_retreinados']}

Aprovação:
  • {aprovacao['geral']['aprovadas']}/{aprovacao['geral']['total']} outputs aprovados ({aprovacao['geral']['taxa_pct']:.1f}%)
  • Meta: 90% → {'✅ ATINGIDA' if aprovacao['geral']['meta_atingida'] else '❌ NÃO ATINGIDA'}

Variável Crítica (PRODUTO_ACETA-01_MOLEFRAC_MIXED):
  • R² final: {critica_info['r2_final']:.4f if critica_info else 'N/A'}
  • Status: {'✅ APROVADO (≥0.95)' if critica_info and critica_info['atingiu_alvo'] else '❌ REPROVADO (<0.95)'}
""")

print("="*80)
print("✅ RELATÓRIO COMPLETO GERADO!")
print("="*80)