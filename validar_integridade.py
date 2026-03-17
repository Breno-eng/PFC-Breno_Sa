"""
════════════════════════════════════════════════════════════════════════════════
    DESCOBRIDOR DE ORDEM REAL (BASEADO NO DATASET)
    
    Como o Scaler está "cego" (sem nomes), a única forma de saber a ordem
    correta é olhando para o arquivo CSV que gerou o treino.
    
    Este script replica a lógica de carregamento de dados para revelar
    a ordem exata das colunas X (Inputs) e y (Outputs).
════════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import yaml
import json
import sys
from pathlib import Path

# Configuração de encoding para Windows
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 1. Configurar Caminhos
BASE_DIR = Path(__file__).resolve().parent.parent
print(f"📂 Raiz: {BASE_DIR}")

try:
    with open(BASE_DIR / "config" / "config.yaml", 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    DATASET_PATH = BASE_DIR / cfg['paths']['dataset']
    CONFIG_JSON_PATH = BASE_DIR / cfg['paths']['output_modelos'] / "config_digital_twin.json"
except Exception as e:
    print(f"❌ Erro ao ler config.yaml: {e}")
    # Tente o caminho padrão se falhar
    DATASET_PATH = BASE_DIR / "datasets_gerados" / "dataset_unificado.csv"

print(f"📂 Lendo Dataset Original: {DATASET_PATH.name}...")

if not DATASET_PATH.exists():
    print(f"❌ Dataset não encontrado em: {DATASET_PATH}")
    sys.exit(1)

# 2. Ler Dataset (Apenas cabeçalho para ser rápido)
df = pd.read_csv(DATASET_PATH, nrows=5)
colunas_totais = list(df.columns)

print(f"   📊 Total colunas no CSV: {len(colunas_totais)}")

# 3. Replicar a lógica de separação (Engenharia Reversa)
# Geralmente: [Metadados] + [Inputs] + [Outputs] + [Lixo/Ignorados]

# A. Identificar Metadados (primeiras colunas geralmente)
# Ajuste essa lista conforme seu padrão de colunas ignoradas
colunas_ignorar = ['ID', 'id', 'original_id', 'fonte_dados', 'data', 'timestamp', 'simulacao']
metadados = [c for c in colunas_totais if c.lower() in colunas_ignorar or 'Unnamed' in c]

# B. Identificar Outputs (baseado no que sabemos do config atual)
try:
    with open(CONFIG_JSON_PATH, 'r', encoding='utf-8') as f:
        js = json.load(f)
        outputs_conhecidos = set(js.get('variaveis', {}).get('outputs', js.get('outputs', [])))
        inputs_listados_no_json = js.get('variaveis', {}).get('inputs', js.get('inputs', []))
except:
    outputs_conhecidos = set()
    inputs_listados_no_json = []

# C. Deduzir Inputs
# Inputs são tudo que NÃO é metadado E NÃO é output
candidatos_input = [c for c in colunas_totais if c not in metadados]

# Separar inputs e outputs baseados na posição ou nome
inputs_reais = []
outputs_reais = []

# Lógica comum: Inputs vêm antes dos Outputs, ou usamos a lista conhecida para filtrar
# Se tivermos a lista de outputs conhecidos, é fácil:
if outputs_conhecidos:
    inputs_reais = [c for c in candidatos_input if c not in outputs_conhecidos]
    outputs_reais = [c for c in candidatos_input if c in outputs_conhecidos]
else:
    # Fallback: Assume que as primeiras 19 colunas após metadados são inputs
    print("⚠️  Lista de outputs não disponível, tentando dedução por posição (primeiros 19)...")
    inputs_reais = candidatos_input[:19]
    outputs_reais = candidatos_input[19:]

print("\n" + "="*80)
print("🔍 RESULTADO DA ANÁLISE FORENSE")
print("="*80)

print(f"✅ INPUTS DETECTADOS ({len(inputs_reais)}):")
print(f"   (Esta é a ordem que o modelo aprendeu)\n")
print(json.dumps(inputs_reais, indent=4))

print("\n" + "-"*80)

# Comparação
if inputs_listados_no_json == inputs_reais:
    print("✅ A ordem no seu JSON atual JÁ ESTÁ CORRETA!")
    print("   Se o R² está ruim, o problema não é a ordem das colunas.")
    print("   Verifique: Unidades de medida (Kelvin vs Celsius, Bar vs Pa) ou Normalização.")
else:
    print("🚨 A ORDEM ESTÁ DIFERENTE! ISSO CAUSA O ERRO.")
    print("   Copie a lista acima e substitua no seu 'config_digital_twin.json'.")
    
    # Mostrar diferenças
    print("\n   Diferenças encontradas (Primeiras 5):")
    for i, (json_val, real_val) in enumerate(zip(inputs_listados_no_json, inputs_reais)):
        if json_val != real_val:
            print(f"   Posição {i}: JSON diz '{json_val}' mas CSV diz '{real_val}'")
            if i >= 4: break

print("="*80 + "\n")