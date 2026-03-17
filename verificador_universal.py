"""
════════════════════════════════════════════════════════════════════════════════
    VERIFICADOR UNIVERSAL DE INPUTS E ORDENS
    
    Este script audita a integridade do Digital Twin comparando:
    1. A "Verdade Absoluta" (Scaler.pkl usado no treino)
    2. O "Mapa do Keras" (config_final.json e config_digital_twin.json)
    3. A "Entrada do Controle" (casos_teste.csv)
    
    Se as colunas não estiverem na mesma linha horizontal, o modelo falhará.
════════════════════════════════════════════════════════════════════════════════
"""

import sys
import io
import json
import joblib
import pandas as pd
import yaml
import os
from pathlib import Path
from itertools import zip_longest

# 🔧 Vacina para Visualização no Windows
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ═══════════════════════════════════════════════════════════════════════════
# 1. SETUP DE CAMINHOS
# ═══════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent.parent
print(f"\n📂 Raiz do Projeto: {BASE_DIR}")

# Tentar carregar config.yaml
try:
    with open(BASE_DIR / "config" / "config.yaml", 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    PASTA_MODELOS = BASE_DIR / cfg['paths']['output_modelos']
    PASTA_CONTROLE = BASE_DIR / "controle"
except:
    print("⚠️  Config.yaml não encontrado ou inválido. Usando caminhos padrão.")
    PASTA_MODELOS = BASE_DIR / "Modelos Keras"
    PASTA_CONTROLE = BASE_DIR / "controle"

# Arquivos a analisar
FILE_SCALER = PASTA_MODELOS / "scaler_X.pkl"
FILE_CONF_DT = PASTA_MODELOS / "config_digital_twin.json"
FILE_CONF_FN = PASTA_MODELOS / "config_final.json"
FILE_CSV = PASTA_CONTROLE / "casos_teste.csv"

# ═══════════════════════════════════════════════════════════════════════════
# 2. COLETA DE DADOS (EXTRAÇÃO)
# ═══════════════════════════════════════════════════════════════════════════

dados = {
    "SCALER": [],
    "CONF_DT": [],
    "CONF_FINAL": [],
    "CSV": []
}

print("\n🔍 INICIANDO AUDITORIA...\n")

# --- A. LER SCALER (A VERDADE DO TREINO) ---
if FILE_SCALER.exists():
    try:
        scaler = joblib.load(FILE_SCALER)
        if hasattr(scaler, 'feature_names_in_'):
            dados["SCALER"] = list(scaler.feature_names_in_)
            print(f"✅ SCALER (Treino): {len(dados['SCALER'])} inputs encontrados.")
        else:
            print("⚠️  SCALER: Arquivo carregado, mas sem nomes de colunas (sklearn antigo?).")
            dados["SCALER"] = ["(Indisponível)"] * 19
    except Exception as e:
        print(f"❌ SCALER: Erro ao ler ({e})")
else:
    print(f"❌ SCALER: Arquivo não encontrado em {FILE_SCALER}")

# --- B. LER CONFIG DIGITAL TWIN ---
if FILE_CONF_DT.exists():
    try:
        with open(FILE_CONF_DT, 'r', encoding='utf-8') as f:
            js = json.load(f)
        if 'variaveis' in js:
            dados["CONF_DT"] = js['variaveis']['inputs']
        else:
            dados["CONF_DT"] = js.get('inputs', [])
        print(f"✅ CONFIG DT: {len(dados['CONF_DT'])} inputs encontrados.")
    except:
        print("❌ CONFIG DT: Erro ao ler.")
else:
    print("⚠️  CONFIG DT: Arquivo não encontrado.")

# --- C. LER CONFIG FINAL ---
if FILE_CONF_FN.exists():
    try:
        with open(FILE_CONF_FN, 'r', encoding='utf-8') as f:
            js = json.load(f)
        dados["CONF_FINAL"] = js.get('inputs', [])
        print(f"✅ CONFIG FINAL: {len(dados['CONF_FINAL'])} inputs encontrados.")
    except:
        print("❌ CONFIG FINAL: Erro ao ler.")
else:
    print("⚠️  CONFIG FINAL: Arquivo não encontrado.")

# --- D. LER CSV DE TESTE ---
if FILE_CSV.exists():
    try:
        df = pd.read_csv(FILE_CSV)
        cols = [c for c in df.columns if c not in ['ID', 'DESCRICAO', 'id', 'descricao']]
        dados["CSV"] = cols
        print(f"✅ CSV TESTE: {len(dados['CSV'])} colunas de dados encontradas.")
    except:
        print("❌ CSV TESTE: Erro ao ler.")
else:
    print("⚠️  CSV TESTE: Arquivo não encontrado.")

# ═══════════════════════════════════════════════════════════════════════════
# 3. TABELA COMPARATIVA
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*145)
print(f"{'IDX':<4} | {'SCALER (O QUE O MODELO PEDE)':<35} | {'CONFIG_DT (O QUE O KERAS LÊ)':<35} | {'CSV (O QUE O CONTROLE MANDA)':<35} | {'STATUS'}")
print("="*145)

max_len = max(len(d) for d in dados.values())
erros_fatals = 0

for i in range(max_len):
    s = dados["SCALER"][i] if i < len(dados["SCALER"]) else "---"
    c = dados["CONF_DT"][i] if i < len(dados["CONF_DT"]) else "---"
    v = dados["CSV"][i] if i < len(dados["CSV"]) else "---"
    
    # Lógica de validação
    match_scaler_config = (s == c)
    match_scaler_csv = (s == v)
    
    if s == "---":
        status = "⚠️ EXTRA"
        cor = ""
    elif s == "(Indisponível)":
        status = "❓ UNKNOWN"
        cor = ""
    elif match_scaler_config and match_scaler_csv:
        status = "✅ OK"
        cor = ""
    elif not match_scaler_config:
        status = "🛑 ERRO MODELO" # Config diferente do Treino
        erros_fatals += 1
        cor = " <--- ERRO AQUI"
    elif not match_scaler_csv:
        status = "⚠️ ERRO CSV"    # CSV diferente do Treino (menos grave se usar dict)
        cor = " <--- CSV DIFERENTE"
    else:
        status = "❓"
        cor = ""

    print(f"{i:<4} | {s:<35} | {c:<35} | {v:<35} | {status}{cor}")

print("="*145 + "\n")

# ═══════════════════════════════════════════════════════════════════════════
# 4. CONCLUSÃO AUTOMÁTICA
# ═══════════════════════════════════════════════════════════════════════════

print("🧠 ANÁLISE DO DIAGNÓSTICO:")

if dados["SCALER"] and dados["SCALER"][0] != "(Indisponível)":
    if dados["SCALER"] == dados["CONF_DT"]:
        print("   ✅ O modulo_keras.py está lendo a ordem correta (Config DT == Scaler).")
    else:
        print("   🛑 PERIGO CRÍTICO: O modulo_keras.py está lendo uma ordem DIFERENTE do treino!")
        print("      Isso causa R² negativo e previsões aleatórias.")
        print("      SOLUÇÃO: Rode o script 'corrigir_ordem.py' imediatamente.")

    if dados["SCALER"] == dados["CSV"]:
        print("   ✅ O sistema_controle.py está enviando o CSV na ordem visual correta.")
    else:
        print("   ⚠️  AVISO: O CSV está visualmente fora de ordem em relação ao modelo.")
        print("      Se o sistema usar mapeamento por nome (dicionário), pode funcionar.")
        print("      Se usar array direto (numpy), vai falhar.")
        print("      SOLUÇÃO: Rode 'criar_casos_teste.py' (versão 2.1+) para recriar o CSV ordenado.")

elif dados["SCALER"] and dados["SCALER"][0] == "(Indisponível)":
    print("   ⚠️  Não foi possível validar a ordem absoluta pois o Scaler não salvou nomes.")
    print("      Você deve confiar que 'config_digital_twin.json' reflete a ordem de criação original.")

print("\n")