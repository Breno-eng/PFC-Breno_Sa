"""
════════════════════════════════════════════════════════════════════════════════
    CRIADOR DE CASOS DE TESTE V3.0
    
    OPÇÕES:
        1. Aleatório     — quantidade, tipo de variação (uniforme/aleatória), seed, extremos
        2. Sensibilidade — variar uma var, todas, ou buscar fronteira
        3. Validar CSV   — verifica e corrige ordem das colunas
════════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import numpy as np
import json
import os
from pathlib import Path
import yaml
import shutil
import joblib

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent.parent
print(f"\n📂 Raiz do Projeto: {BASE_DIR}")

with open(BASE_DIR / "config" / "config.yaml", 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

PASTA_MODELOS  = BASE_DIR / cfg['paths']['output_modelos']
CONFIG_DT_PATH = PASTA_MODELOS / "config_digital_twin.json"
SCALER_PATH    = PASTA_MODELOS / "scaler_X.pkl"
PASTA_CONTROLE = BASE_DIR / "controle"
PASTA_CONTROLE.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# CARREGAR ORDEM E VALORES
# ═══════════════════════════════════════════════════════════════════════════

print("\n🔍 Carregando configurações do modelo...")

ORDEM_INPUTS    = None
VALORES_TIPICOS = {}
VALORES_MIN     = {}
VALORES_MAX     = {}

# Scaler — fonte da verdade da ordem
if SCALER_PATH.exists():
    try:
        scaler = joblib.load(SCALER_PATH)
        if hasattr(scaler, 'feature_names_in_'):
            ORDEM_INPUTS = list(scaler.feature_names_in_)
            print(f"   ✅ Ordem do scaler ({len(ORDEM_INPUTS)} inputs)")
    except Exception as e:
        print(f"   ⚠️  Erro ao ler scaler: {e}")

# config_digital_twin.json — valores típicos e ranges
with open(CONFIG_DT_PATH, 'r', encoding='utf-8') as f:
    config_dt = json.load(f)

if ORDEM_INPUTS is None:
    ORDEM_INPUTS = config_dt.get('variaveis', {}).get('inputs',
                   config_dt.get('inputs', config_dt.get('nomes_inputs', [])))
    print(f"   ✅ Ordem do config ({len(ORDEM_INPUTS)} inputs)")

est = config_dt.get('estatisticas_inputs', {})
if 'valores_tipicos' in est:
    VALORES_TIPICOS = est['valores_tipicos']
    VALORES_MIN     = est.get('valores_min', {})
    VALORES_MAX     = est.get('valores_max', {})
elif 'valores_tipicos' in config_dt:
    VALORES_TIPICOS = config_dt['valores_tipicos']

TARGET_VARIABLE = "PRODUTO_ACETA-01_MOLEFRAC_MIXED"
LIMITE_TARGET   = config_dt.get('variaveis_criticas', {}).get('limites', {}).get(
                    TARGET_VARIABLE, {}).get('valor', 0.95)

print(f"   ✅ Valores típicos: {len(VALORES_TIPICOS)} variáveis")
print(f"   🎯 Limite crítico [{TARGET_VARIABLE}]: {LIMITE_TARGET}")

if not ORDEM_INPUTS or not VALORES_TIPICOS:
    print("\n❌ Erro ao carregar configurações!"); exit(1)

# Calcular ranges reais (±60% do típico se não disponível no config)
for var in ORDEM_INPUTS:
    tipico = VALORES_TIPICOS.get(var, 0.0)
    if var not in VALORES_MIN:
        VALORES_MIN[var] = tipico * 0.40
    if var not in VALORES_MAX:
        VALORES_MAX[var] = tipico * 1.60

# ═══════════════════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════

def identificar_torres(inputs):
    torres = {}
    for var in inputs:
        if any(x in var for x in ['NSTAGE', 'FEED_STAGE']):
            torre = var.split('_')[0]
            if torre not in torres:
                torres[torre] = {}
            if 'NSTAGE' in var:
                torres[torre]['nstage'] = var
            elif 'FEED_STAGE' in var:
                torres[torre]['feed'] = var
    return torres

def corrigir_torres(caso, torres):
    for torre, cols in torres.items():
        if 'nstage' in cols and 'feed' in cols:
            ns = max(2, int(round(float(caso[cols['nstage']]))))
            fs = max(1, min(int(round(float(caso[cols['feed']]))), ns - 1))
            caso[cols['nstage']] = ns
            caso[cols['feed']]   = fs
    return caso

def garantir_ordem(df):
    cols = ['ID', 'DESCRICAO'] + ORDEM_INPUTS
    for col in cols:
        if col not in df.columns and col not in ['ID', 'DESCRICAO']:
            df[col] = VALORES_TIPICOS.get(col, 0.0)
    return df[cols]

def salvar(casos, descricao_arquivo="casos"):
    if not casos:
        print("\n❌ Nenhum caso gerado.\n"); return

    df = pd.DataFrame(casos)
    df = garantir_ordem(df)
    df['ID'] = df['ID'].astype(int)
    for col in df.columns:
        if any(x in col for x in ['NSTAGE', 'FEED_STAGE']):
            df[col] = df[col].astype(int)

    csv_path = PASTA_CONTROLE / 'casos_teste.csv'
    df.to_csv(csv_path, index=False, float_format='%.4f')

    print(f"\n{'='*60}")
    print(f"  ✅ {len(df)} casos salvos → {csv_path.name}")
    print(f"  📋 {len(ORDEM_INPUTS)} inputs | Ordem: ✅")
    print(f"{'='*60}\n")

torres_map = identificar_torres(ORDEM_INPUTS)

# ═══════════════════════════════════════════════════════════════════════════
# MENU PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("  CRIADOR DE CASOS DE TESTE V3.0".center(60))
print(f"{'='*60}\n")
print("  1. Aleatório")
print("  2. Sensibilidade / Fronteira")
print("  3. Validar CSV existente\n")

opcao = input("Escolha (1-3): ").strip()

# ═══════════════════════════════════════════════════════════════════════════
# OPÇÃO 1: ALEATÓRIO
# ═══════════════════════════════════════════════════════════════════════════

if opcao == '1':
    print("\n🎲 GERAÇÃO ALEATÓRIA\n")

    n = int(input("   Quantidade de casos [100]: ").strip() or "100")

    # ── Tipo de variação ──────────────────────────────────────────────────
    print("\n   Tipo de variação:")
    print("     u. Uniforme  — mesmo % para todas as variáveis")
    print("     a. Aleatória — cada variável recebe um % sorteado entre 2% e 60%")
    tipo_var = input("   Tipo (u/a) [u]: ").strip().lower() or "u"

    if tipo_var == 'a':
        var_pct_global = None  # será sorteado individualmente por variável/caso
        print(f"\n   📊 Variação: Aleatória por variável (2% a 60%)")
    else:
        tipo_var = 'u'  # garante valor padrão caso entrada inválida
        var_pct_global = float(input("   Variação % [60]: ").strip() or "60") / 100
        print(f"\n   📊 Variação: Uniforme ±{var_pct_global*100:.0f}%")

    seed_str = input("   Seed [Enter = aleatório]: ").strip()
    extremos = input("   Incluir casos extremos? (s/n) [n]: ").strip().lower() == 's'

    if seed_str:
        np.random.seed(int(seed_str))
        print(f"   🔒 Seed fixo: {seed_str}")
    else:
        print(f"   🎲 Seed aleatório")

    print(f"   📦 Casos extremos: {'Sim' if extremos else 'Não'}")
    print(f"\n⏳ Gerando {n} casos...\n")

    casos = []
    for i in range(1, n + 1):
        caso = {'ID': i, 'DESCRICAO': f'Aleatorio {i}'}
        for var in ORDEM_INPUTS:
            if any(x in var for x in ['NSTAGE', 'FEED_STAGE']):
                continue
            tipico = VALORES_TIPICOS.get(var, 0.0)
            vmin   = VALORES_MIN.get(var, tipico * 0.40)
            vmax   = VALORES_MAX.get(var, tipico * 1.60)

            # Determinar o % de variação efetivo para esta variável/caso
            if tipo_var == 'a':
                var_pct = np.random.uniform(0.02, 0.60)  # sorteado entre 2% e 60%
            else:
                var_pct = var_pct_global

            # Respeitar range do dataset (não ultrapassar min/max do config)
            efetivo_min = max(vmin, tipico * (1 - var_pct))
            efetivo_max = min(vmax, tipico * (1 + var_pct))
            caso[var] = np.random.uniform(efetivo_min, efetivo_max)

        # Torres
        for var in ORDEM_INPUTS:
            if 'NSTAGE' in var:
                caso[var] = np.random.randint(2, 9)
            elif 'FEED_STAGE' in var:
                caso[var] = 2

        caso = corrigir_torres(caso, torres_map)
        casos.append(caso)

    # Casos extremos
    if extremos:
        id_extra = n + 1
        # Mínimos
        caso_min = {'ID': id_extra, 'DESCRICAO': 'Extremo_MIN'}
        for var in ORDEM_INPUTS:
            if any(x in var for x in ['NSTAGE', 'FEED_STAGE']):
                continue
            caso_min[var] = VALORES_MIN.get(var, VALORES_TIPICOS.get(var, 0.0) * 0.4)
        for var in ORDEM_INPUTS:
            if 'NSTAGE' in var: caso_min[var] = 2
            elif 'FEED_STAGE' in var: caso_min[var] = 1
        casos.append(corrigir_torres(caso_min, torres_map))
        id_extra += 1

        # Máximos
        caso_max = {'ID': id_extra, 'DESCRICAO': 'Extremo_MAX'}
        for var in ORDEM_INPUTS:
            if any(x in var for x in ['NSTAGE', 'FEED_STAGE']):
                continue
            caso_max[var] = VALORES_MAX.get(var, VALORES_TIPICOS.get(var, 0.0) * 1.6)
        for var in ORDEM_INPUTS:
            if 'NSTAGE' in var: caso_max[var] = 8
            elif 'FEED_STAGE' in var: caso_max[var] = 2
        casos.append(corrigir_torres(caso_max, torres_map))

        print(f"   ✅ + 2 casos extremos (MIN e MAX)\n")

    salvar(casos)

# ═══════════════════════════════════════════════════════════════════════════
# OPÇÃO 2: SENSIBILIDADE / FRONTEIRA
# ═══════════════════════════════════════════════════════════════════════════

elif opcao == '2':
    print("\n📊 SENSIBILIDADE / FRONTEIRA\n")
    print("   a. Variar UMA variável (resto típico)")
    print("   b. Variar TODAS sistematicamente")
    print("   c. Buscar fronteira (próximo ao limite crítico)\n")

    modo = input("   Modo (a/b/c): ").strip().lower()

    # ── Modo A: Uma variável ──────────────────────────────────────────────
    if modo == 'a':
        print(f"\n   Variáveis disponíveis:")
        for i, var in enumerate(ORDEM_INPUTS, 1):
            tipico = VALORES_TIPICOS.get(var, 0)
            vmin   = VALORES_MIN.get(var, tipico * 0.4)
            vmax   = VALORES_MAX.get(var, tipico * 1.6)
            print(f"   {i:2d}. {var:<25} típico={tipico:.3f}  [{vmin:.3f} → {vmax:.3f}]")

        idx      = int(input("\n   Número da variável: ").strip()) - 1
        var_escolhida = ORDEM_INPUTS[idx]
        n_pontos = int(input(f"   Pontos para '{var_escolhida}' [20]: ").strip() or "20")

        tipico = VALORES_TIPICOS.get(var_escolhida, 0.0)
        vmin   = VALORES_MIN.get(var_escolhida, tipico * 0.4)
        vmax   = VALORES_MAX.get(var_escolhida, tipico * 1.6)

        vmin_custom = input(f"   Valor mínimo [{vmin:.4f}]: ").strip()
        vmax_custom = input(f"   Valor máximo [{vmax:.4f}]: ").strip()
        vmin = float(vmin_custom) if vmin_custom else vmin
        vmax = float(vmax_custom) if vmax_custom else vmax

        print(f"\n⏳ Gerando {n_pontos} casos variando '{var_escolhida}' de {vmin:.4f} a {vmax:.4f}...\n")

        casos = []
        valores = np.linspace(vmin, vmax, n_pontos)
        for i, val in enumerate(valores, 1):
            caso = {'ID': i, 'DESCRICAO': f'Sens_{var_escolhida}_{val:.4f}'}
            for var in ORDEM_INPUTS:
                if any(x in var for x in ['NSTAGE', 'FEED_STAGE']): continue
                caso[var] = val if var == var_escolhida else VALORES_TIPICOS.get(var, 0.0)
            for var in ORDEM_INPUTS:
                if 'NSTAGE' in var:   caso[var] = int(VALORES_TIPICOS.get(var, 4))
                elif 'FEED_STAGE' in var: caso[var] = int(VALORES_TIPICOS.get(var, 2))
            caso = corrigir_torres(caso, torres_map)
            casos.append(caso)

        salvar(casos, f"sensibilidade_{var_escolhida}")

    # ── Modo B: Todas as variáveis ────────────────────────────────────────
    elif modo == 'b':
        n_pontos = int(input("   Pontos por variável [10]: ").strip() or "10")
        print(f"\n⏳ Gerando {n_pontos} × {len(ORDEM_INPUTS)} = {n_pontos * len(ORDEM_INPUTS)} casos...\n")

        casos = []
        id_counter = 1
        for var_escolhida in ORDEM_INPUTS:
            if any(x in var_escolhida for x in ['NSTAGE', 'FEED_STAGE']):
                continue
            tipico = VALORES_TIPICOS.get(var_escolhida, 0.0)
            vmin   = VALORES_MIN.get(var_escolhida, tipico * 0.4)
            vmax   = VALORES_MAX.get(var_escolhida, tipico * 1.6)

            for val in np.linspace(vmin, vmax, n_pontos):
                caso = {'ID': id_counter, 'DESCRICAO': f'Sens_{var_escolhida}'}
                for var in ORDEM_INPUTS:
                    if any(x in var for x in ['NSTAGE', 'FEED_STAGE']): continue
                    caso[var] = val if var == var_escolhida else VALORES_TIPICOS.get(var, 0.0)
                for var in ORDEM_INPUTS:
                    if 'NSTAGE' in var:       caso[var] = int(VALORES_TIPICOS.get(var, 4))
                    elif 'FEED_STAGE' in var: caso[var] = int(VALORES_TIPICOS.get(var, 2))
                caso = corrigir_torres(caso, torres_map)
                casos.append(caso)
                id_counter += 1

        salvar(casos, "sensibilidade_todas")

    # ── Modo C: Fronteira ─────────────────────────────────────────────────
    elif modo == 'c':
        print(f"\n   Gera casos ao redor do limite crítico ({LIMITE_TARGET})")
        print(f"   O Keras vai disparar alarme em alguns → você vê onde está a fronteira\n")

        print(f"   Variáveis disponíveis:")
        for i, var in enumerate(ORDEM_INPUTS, 1):
            tipico = VALORES_TIPICOS.get(var, 0)
            print(f"   {i:2d}. {var:<25} típico={tipico:.3f}")

        idx           = int(input("\n   Número da variável principal: ").strip()) - 1
        var_principal = ORDEM_INPUTS[idx]
        n_pontos      = int(input(f"   Pontos na fronteira [30]: ").strip() or "30")
        n_ruido       = int(input(f"   Variáveis secundárias com ruído (0=nenhuma) [3]: ").strip() or "3")
        seed_str      = input("   Seed [Enter = aleatório]: ").strip()

        if seed_str:
            np.random.seed(int(seed_str))

        tipico = VALORES_TIPICOS.get(var_principal, 0.0)
        vmin   = VALORES_MIN.get(var_principal, tipico * 0.4)
        vmax   = VALORES_MAX.get(var_principal, tipico * 1.6)

        # Concentrar os pontos na faixa intermediária (onde a fronteira provavelmente está)
        p_baixo = 0.3   # 30% dos pontos na faixa baixa
        p_medio = 0.5   # 50% dos pontos na faixa media (fronteira)
        p_alto  = 0.2   # 20% dos pontos na faixa alta

        n_baixo = int(n_pontos * p_baixo)
        n_medio = int(n_pontos * p_medio)
        n_alto  = n_pontos - n_baixo - n_medio

        v_baixo = np.linspace(vmin,                   tipico * 0.75, n_baixo)
        v_medio = np.linspace(tipico * 0.75,          tipico * 1.10, n_medio)
        v_alto  = np.linspace(tipico * 1.10,          vmax,          n_alto)
        valores = np.concatenate([v_baixo, v_medio, v_alto])
        np.random.shuffle(valores)

        # Variáveis secundárias com ruído
        vars_ruido = []
        outras_vars = [v for v in ORDEM_INPUTS
                       if v != var_principal
                       and not any(x in v for x in ['NSTAGE','FEED_STAGE'])]
        if n_ruido > 0 and outras_vars:
            vars_ruido = list(np.random.choice(outras_vars,
                              size=min(n_ruido, len(outras_vars)), replace=False))
            print(f"\n   Ruído em: {', '.join(vars_ruido)}")

        print(f"\n⏳ Gerando {n_pontos} casos de fronteira para '{var_principal}'...\n")

        casos = []
        for i, val in enumerate(valores, 1):
            caso = {'ID': i, 'DESCRICAO': f'Fronteira_{var_principal}_{val:.4f}'}
            for var in ORDEM_INPUTS:
                if any(x in var for x in ['NSTAGE', 'FEED_STAGE']): continue
                if var == var_principal:
                    caso[var] = val
                elif var in vars_ruido:
                    tipico_v = VALORES_TIPICOS.get(var, 0.0)
                    caso[var] = tipico_v * np.random.uniform(0.95, 1.05)  # ±5% de ruído
                else:
                    caso[var] = VALORES_TIPICOS.get(var, 0.0)

            for var in ORDEM_INPUTS:
                if 'NSTAGE' in var:       caso[var] = int(VALORES_TIPICOS.get(var, 4))
                elif 'FEED_STAGE' in var: caso[var] = int(VALORES_TIPICOS.get(var, 2))

            caso = corrigir_torres(caso, torres_map)
            casos.append(caso)

        salvar(casos, f"fronteira_{var_principal}")

    else:
        print(f"\n❌ Modo '{modo}' inválido.\n")

# ═══════════════════════════════════════════════════════════════════════════
# OPÇÃO 3: VALIDAR CSV
# ═══════════════════════════════════════════════════════════════════════════

elif opcao == '3':
    csv_path = PASTA_CONTROLE / 'casos_teste.csv'
    if not csv_path.exists():
        print(f"\n❌ Arquivo não encontrado: {csv_path}\n"); exit(0)

    print(f"\n🔍 Validando {csv_path.name}...\n")
    df = pd.read_csv(csv_path)
    colunas_csv = [c for c in df.columns if c not in ['ID', 'DESCRICAO']]

    print(f"   Casos:  {len(df)}")
    print(f"   Inputs: {len(colunas_csv)}")

    if colunas_csv == ORDEM_INPUTS:
        print("   ✅ Ordem das colunas CORRETA!\n")
    else:
        print("   ⚠️  Ordem INCORRETA!")
        print(f"   Esperado:   {ORDEM_INPUTS[:3]}...")
        print(f"   Encontrado: {colunas_csv[:3]}...")
        if input("\n   Corrigir automaticamente? (s/n): ").lower() == 's':
            shutil.copy2(csv_path, csv_path.with_suffix('.backup.csv'))
            df = garantir_ordem(df)
            df.to_csv(csv_path, index=False, float_format='%.4f')
            print("   ✅ Corrigido e salvo!\n")

else:
    print(f"\n❌ Opção '{opcao}' inválida.\n")