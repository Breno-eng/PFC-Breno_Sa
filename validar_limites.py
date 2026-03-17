"""
════════════════════════════════════════════════════════════════════════════════
    VALIDADOR DE LIMITES CRÍTICOS - Digital Twin
    
    Verifica se os limites configurados estão calibrados corretamente
    comparando com os dados históricos do dataset de treinamento
════════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import json

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_PATH = r"C:\DigitalTwin\Modelos Keras\config_digital_twin.json"
DATASET_PATH = r"C:\DigitalTwin\2_datasets_gerados\dataset_unificado.csv"

# ═══════════════════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("VALIDADOR DE LIMITES CRÍTICOS".center(80))
print("="*80 + "\n")

print("📂 Carregando dataset CSV...")
df = pd.read_csv(DATASET_PATH)
print(f"   ✅ {len(df)} casos carregados\n")

print("📂 Carregando configuração...")
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)
print(f"   ✅ {len(config['limites_criticos'])} limites configurados\n")

# ═══════════════════════════════════════════════════════════════════════════
# VALIDAR CADA LIMITE
# ═══════════════════════════════════════════════════════════════════════════

print("="*80)
print("ANÁLISE DE LIMITES".center(80))
print("="*80 + "\n")

limites_ok = 0
limites_problematicos = 0

for var_name, limite in config['limites_criticos'].items():
    if var_name in df.columns:
        print(f"📊 {var_name}:")
        print(f"   Limite configurado: {limite['tipo']} {limite['valor']:.2f}°C")
        print(f"   Dataset:")
        print(f"      Mínimo:  {df[var_name].min():.2f}°C")
        print(f"      Média:   {df[var_name].mean():.2f}°C")
        print(f"      Máximo:  {df[var_name].max():.2f}°C")
        
        if limite['tipo'] == 'max':
            casos_acima = (df[var_name] > limite['valor']).sum()
            pct_violacoes = casos_acima / len(df) * 100
            print(f"      Casos ACIMA do limite: {casos_acima} ({pct_violacoes:.2f}%)")
            
            if pct_violacoes > 50:
                print(f"      🚨 CRÍTICO: Mais de 50% dos casos violam o limite!")
                print(f"      💡 Sugestão: Aumente para {df[var_name].quantile(0.95):.2f}°C (95º percentil)")
                limites_problematicos += 1
            elif pct_violacoes > 10:
                print(f"      ⚠️  Aviso: {pct_violacoes:.1f}% dos casos violam o limite")
                print(f"      💡 Considere ajustar para: {df[var_name].quantile(0.90):.2f}°C (90º percentil)")
                limites_problematicos += 1
            else:
                print(f"      ✅ Limite adequado! ({pct_violacoes:.2f}% de violações)")
                limites_ok += 1
        
        elif limite['tipo'] == 'min':
            casos_abaixo = (df[var_name] < limite['valor']).sum()
            pct_violacoes = casos_abaixo / len(df) * 100
            print(f"      Casos ABAIXO do limite: {casos_abaixo} ({pct_violacoes:.2f}%)")
            
            if pct_violacoes > 50:
                print(f"      🚨 CRÍTICO: Mais de 50% dos casos violam o limite!")
                print(f"      💡 Sugestão: Reduza para {df[var_name].quantile(0.05):.2f}°C (5º percentil)")
                limites_problematicos += 1
            elif pct_violacoes > 10:
                print(f"      ⚠️  Aviso: {pct_violacoes:.1f}% dos casos violam o limite")
                print(f"      💡 Considere ajustar para: {df[var_name].quantile(0.10):.2f}°C (10º percentil)")
                limites_problematicos += 1
            else:
                print(f"      ✅ Limite adequado! ({pct_violacoes:.2f}% de violações)")
                limites_ok += 1
        
        print()
    else:
        print(f"❌ {var_name}: NÃO encontrado no dataset!")
        print(f"   Verifique se o nome está correto em config_digital_twin.json\n")
        limites_problematicos += 1

# ═══════════════════════════════════════════════════════════════════════════
# RESUMO FINAL
# ═══════════════════════════════════════════════════════════════════════════

print("="*80)
print("RESUMO".center(80))
print("="*80 + "\n")

total = limites_ok + limites_problematicos

if total > 0:
    print(f"📊 Total de limites: {total}")
    print(f"   ✅ Adequados:        {limites_ok} ({limites_ok/total*100:.1f}%)")
    print(f"   ⚠️  Problemáticos:   {limites_problematicos} ({limites_problematicos/total*100:.1f}%)")
    print()
    
    if limites_problematicos == 0:
        print("🎉 TODOS OS LIMITES ESTÃO BEM CALIBRADOS!")
        print("   Você pode executar o Digital Twin com confiança.\n")
    elif limites_problematicos < total / 2:
        print("⚠️  ALGUNS LIMITES PRECISAM DE AJUSTE")
        print("   Revise as sugestões acima antes de executar testes críticos.\n")
    else:
        print("🚨 ATENÇÃO: MAIORIA DOS LIMITES PRECISA DE AJUSTE!")
        print("   Recomenda-se ajustar os limites antes de continuar.\n")
else:
    print("❌ Nenhum limite configurado para validar.\n")

print("="*80 + "\n")