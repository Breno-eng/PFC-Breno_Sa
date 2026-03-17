import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch
import seaborn as sns
import tensorflow as tf
import logging
tf.get_logger().setLevel(logging.ERROR)
from tensorflow import keras
from tensorflow.keras import layers, callbacks
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.linear_model import LinearRegression, Ridge
import pickle
import joblib
import json
from pathlib import Path
import yaml
import warnings
import os

# ==============================================================================
# 🚑 KIT DE PRIMEIROS SOCORROS DA GPU
# ==============================================================================
os.environ['TF_XLA_FLAGS']         = '--tf_xla_enable_xla_devices=false'
os.environ['TF_XLA_AUTO_JIT']      = '0'
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf
warnings.filterwarnings('ignore')

# ==============================================================================
# ⚙️ CARREGAMENTO DE CONFIGURAÇÕES (YAML)
# ==============================================================================

BASE_DIR    = Path(__file__).resolve().parent.parent
config_path = BASE_DIR / "config" / "config.yaml"

print(f"📂 Raiz do Projeto detectada: {BASE_DIR}")

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    print("✅ Configurações carregadas com sucesso!")
except FileNotFoundError:
    raise FileNotFoundError(f"❌ Config não encontrado em: {config_path}")

# Sementes
SEED = cfg['project']['seed']
np.random.seed(SEED)
tf.random.set_seed(SEED)

# Caminhos
DATASET_PATH             = BASE_DIR / cfg['paths']['dataset']
OUTPUT_PATH              = BASE_DIR / cfg['paths']['output_visualizacoes']
MODELO_PATH              = BASE_DIR / cfg['paths']['output_modelos']
ANALISE_PATH             = BASE_DIR / cfg['paths']['output_analise']
METRICAS_PATH            = BASE_DIR / cfg['paths']['output_metricas']
ESPECIALISTAS_PATH       = MODELO_PATH / 'especialistas'
CAMINHO_FILTRO_QUALIDADE = BASE_DIR / cfg['paths']['filtro_qualidade']

for path in [OUTPUT_PATH, MODELO_PATH, ANALISE_PATH, ESPECIALISTAS_PATH, METRICAS_PATH]:
    os.makedirs(path, exist_ok=True)

# Variáveis e limiares
VARIAVEIS_CRITICAS   = cfg['variables']['critical']
LIMITE_R2_CRITICO    = cfg['thresholds']['r2_critical']
LIMITE_R2_NORMAL     = cfg['thresholds']['r2_normal']
LIMITE_R2_MINIMO     = cfg['thresholds']['r2_minimum']
PERCENTUAL_APROVACAO = cfg['thresholds']['approval_target']

# Flags
REMOVER_DATASET_EXTREMOS = cfg['flags']['remove_extreme_data']
APLICAR_FILTRO_QUALIDADE = cfg['flags']['apply_quality_filter']
REMOVER_OUTPUTS_RUINS    = cfg['flags']['remove_bad_outputs']

# Treino
LR_BASE         = cfg['training']['base_model']['lr']
EPOCHS_BASE     = cfg['training']['base_model']['epochs']
BATCH_SIZE_BASE = cfg['training']['base_model']['batch_size']
PATIENCE_BASE   = cfg['training']['base_model']['patience']

MAX_TENTATIVAS_RETREINO  = cfg['training']['retraining']['max_attempts_normal']
MAX_TENTATIVAS_CRITICAS  = cfg['training']['retraining']['max_attempts_critical']
AJUSTE_LR_RETREINO       = cfg['training']['retraining']['lr_decay']
AUMENTO_EPOCHS_RETREINO  = cfg['training']['retraining']['epochs_increase']

print("="*80)
print(f"MODELO: {cfg['project']['name']} (v{cfg['project']['version']})")
print("="*80)
print(f"🎯 Variáveis Críticas (R² >= {LIMITE_R2_CRITICO}):")
for var in VARIAVEIS_CRITICAS:
    print(f"   • {var}")
print(f"📂 Dataset: {DATASET_PATH}")
print(f"💾 Modelos: {MODELO_PATH}")
print("="*80)

# ==============================================================================
# 🎮 VERIFICAÇÃO GPU
# ==============================================================================
print(f"\n🎮 Verificando GPU...")
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    print(f"   ✅ GPU disponível! ({len(gpus)} dispositivo(s))")
    for gpu in gpus:
        try:
            tf.config.experimental.set_memory_growth(gpu, True)
        except Exception:
            pass
else:
    print(f"   ⚠️  GPU não detectada - usando CPU")

# ==============================================================================
# 📂 FUNÇÕES AUXILIARES
# ==============================================================================

def smape_vec(y_true, y_pred):
    numerator   = np.abs(y_true - y_pred)
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2
    mask = denominator > 1e-10
    if mask.sum() == 0:
        return 0.0
    return np.mean(numerator[mask] / denominator[mask]) * 100

def mape_vec(y_true, y_pred):
    mask = np.abs(y_true) > 1e-10
    if mask.sum() == 0:
        return 0.0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def inverter_transformacao_seletiva(y_pred, indices_transformados):
    if len(indices_transformados) > 0:
        for i in indices_transformados:
            y_pred[:, i] = 1 / (1 + np.exp(-y_pred[:, i]))
    return y_pred

def logit_transform(y_data, epsilon=1e-7):
    y_clip = np.clip(y_data, epsilon, 1 - epsilon)
    return np.log(y_clip / (1 - y_clip))

def inverse_logit(y_logit):
    return 1 / (1 + np.exp(-y_logit))

# ==============================================================================
# 🏗️ ARQUITETURAS
# ==============================================================================

def build_simple_model(input_dim, output_dim, lr=0.001):
    inputs = keras.Input(shape=(input_dim,), name='inputs')
    x = layers.Dense(2048, activation='elu')(inputs)
    x = layers.BatchNormalization()(x)
    x = layers.Dense(1024, activation='elu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dense(1024, activation='elu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.2)(x)
    x = layers.Dense(512, activation='elu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dense(512, activation='elu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.2)(x)
    x = layers.Dense(256, activation='elu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dense(256, activation='elu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(output_dim, name='output')(x)
    model = keras.Model(inputs=inputs, outputs=outputs, name="Simple_MLP")
    model.compile(optimizer=keras.optimizers.Adamax(learning_rate=lr),
                  loss='mse', metrics=['mae'])
    return model

def criar_modelo_especializado(n_inputs, n_outputs_especializados, lr):
    inputs = keras.Input(shape=(n_inputs,))
    x = layers.Dense(1024, activation='elu',
                     kernel_regularizer=keras.regularizers.l2(0.001),
                     name='esp_layer_1')(inputs)
    x = layers.BatchNormalization(name='esp_bn_1')(x)
    x = layers.Dropout(0.15, name='esp_dropout_1')(x)
    x = layers.Dense(512, activation='elu',
                     kernel_regularizer=keras.regularizers.l2(0.001),
                     name='esp_layer_2')(x)
    x = layers.BatchNormalization(name='esp_bn_2')(x)
    x = layers.Dropout(0.15, name='esp_dropout_2')(x)
    x = layers.Dense(256, activation='elu',
                     kernel_regularizer=keras.regularizers.l2(0.001),
                     name='esp_layer_3')(x)
    x = layers.BatchNormalization(name='esp_bn_3')(x)
    x = layers.Dropout(0.075, name='esp_dropout_3')(x)
    x = layers.Dense(256, activation='elu', name='esp_layer_4')(x)
    x = layers.BatchNormalization(name='esp_bn_4')(x)
    outputs = layers.Dense(n_outputs_especializados, name='output')(x)
    model = keras.Model(inputs=inputs, outputs=outputs, name="Especialista")
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr, clipnorm=1.0),
        loss='mse', metrics=['mae'])
    return model

# ==============================================================================
# 📊 CARREGAMENTO E PREPARAÇÃO DE DADOS
# ==============================================================================

print(f"\n📂 Carregando dataset...")
df = pd.read_csv(DATASET_PATH)
print(f"   ✅ {df.shape[0]:,} linhas × {df.shape[1]:,} colunas")

metadados          = list(df.columns[0:2])
inputs_detectados  = list(df.columns[2:21])
outputs_detectados = list(df.columns[21:-3])
excluidas          = list(df.columns[-3:])

print(f"\nInputs ({len(inputs_detectados)}):")
for i, col in enumerate(inputs_detectados):
    print(f"  {i:>2}. {col}")

print(f"\n📋 Estrutura:")
print(f"   • Inputs:  {len(inputs_detectados)}")
print(f"   • Outputs: {len(outputs_detectados)}")

# Verificar variáveis críticas
print(f"\n🔍 Verificando variáveis críticas...")
variaveis_criticas_encontradas     = []
variaveis_criticas_nao_encontradas = []

for var in VARIAVEIS_CRITICAS:
    if var in outputs_detectados:
        variaveis_criticas_encontradas.append(var)
        print(f"   ✅ {var}")
    else:
        variaveis_criticas_nao_encontradas.append(var)
        print(f"   ❌ {var} - NÃO ENCONTRADA!")

# Fonte dos dados
if 'fonte_dados' in df.columns:
    print(f"\n📊 Fontes detectadas:")
    for fonte, qtd in df['fonte_dados'].value_counts(dropna=False).items():
        print(f"   • {fonte}: {qtd:,}")

# Remover extremos
if REMOVER_DATASET_EXTREMOS and 'fonte_dados' in df.columns:
    linhas_antes = len(df)
    df = df[~df['fonte_dados'].str.contains('extremo', case=False, na=False)].copy()
    print(f"\n🚫 Extremos removidos: {linhas_antes - len(df):,} linhas")

# Filtro de qualidade
if APLICAR_FILTRO_QUALIDADE:
    try:
        df_remover = pd.read_csv(CAMINHO_FILTRO_QUALIDADE)
        colunas_sugeridas = df_remover['coluna'].tolist()
        colunas_remover   = [c for c in colunas_sugeridas if c not in VARIAVEIS_CRITICAS]
        protegidas        = [c for c in colunas_sugeridas if c in VARIAVEIS_CRITICAS]

        if protegidas:
            print(f"\n🛡️  Protegidas (críticas):")
            for p in protegidas:
                print(f"   • {p}")

        antes = len(outputs_detectados)
        outputs_detectados = [c for c in outputs_detectados if c not in colunas_remover]
        print(f"\n🔍 Filtro de qualidade: {antes - len(outputs_detectados)} removidos")
    except Exception as e:
        print(f"\n⚠️  Erro no filtro: {e}")

# Filtros automáticos
outputs_iniciais = len(outputs_detectados)
for col in outputs_detectados.copy():
    if df[col].dtype not in ['int64', 'float64']:
        outputs_detectados.remove(col)
    elif df[col].std() <= 1e-10:
        outputs_detectados.remove(col)

print(f"\n✅ Outputs finais: {len(outputs_detectados)} ({len(outputs_detectados)/outputs_iniciais*100:.1f}%)")

# Limpar dados
df_clean = df[inputs_detectados + outputs_detectados].copy()
df_clean = df_clean.dropna().replace([np.inf, -np.inf], np.nan).dropna()
print(f"   Dataset limpo: {len(df_clean):,} linhas")

X = df_clean[inputs_detectados].values
y = df_clean[outputs_detectados].values

# ==============================================================================
# ⚖️ BALANCEAMENTO DO DATASET
# ==============================================================================

BALANCEAR_DATASET       = True
VARIAVEIS_BALANCEAMENTO = VARIAVEIS_CRITICAS
N_AMOSTRAS_DOMINANTE    = 60_000
SEED_BAL                = SEED

if BALANCEAR_DATASET and len(VARIAVEIS_BALANCEAMENTO) > 0:
    print(f"\n" + "="*80)
    print("⚖️  BALANCEAMENTO DO DATASET")
    print("="*80)

    var_guia = VARIAVEIS_BALANCEAMENTO[0]

    if var_guia in outputs_detectados:
        idx_guia  = outputs_detectados.index(var_guia)
        col_guia  = y[:, idx_guia]

        print(f"\n📊 Variável guia: {var_guia}")
        faixas = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
        for lo, hi in faixas:
            mask = (col_guia >= lo) & (col_guia < hi)
            print(f"   [{lo:.1f}-{hi:.1f}): {mask.sum():>7,}  ({mask.sum()/len(col_guia)*100:.1f}%)")

        idx_alta  = np.where(col_guia >= 0.9)[0]
        idx_media = np.where((col_guia >= 0.5) & (col_guia < 0.9))[0]
        idx_baixa = np.where(col_guia < 0.5)[0]

        rng         = np.random.default_rng(SEED_BAL)
        n_alta      = min(N_AMOSTRAS_DOMINANTE, len(idx_alta))
        idx_alta_bal = rng.choice(idx_alta, size=n_alta, replace=False)
        idx_bal      = np.concatenate([idx_alta_bal, idx_media, idx_baixa])
        rng.shuffle(idx_bal)

        X = X[idx_bal]
        y = y[idx_bal]

        print(f"\n   Total depois: {len(X):,}")
        print(f"   ✅ Balanceamento concluído!")
    else:
        print(f"\n⚠️  Variável guia '{var_guia}' não encontrada. Pulando.")
else:
    print(f"\n✅ Balanceamento desativado — {len(X):,} amostras")

# ==============================================================================
# DIAGNÓSTICO DE TARGETS
# ==============================================================================

INDICES_TRANSFORMADOS = []
USA_TRANSFORM         = None

# (Logit desabilitado — mude `if False` para `if len(indices_fracoes) > 0` para habilitar)
if False:
    pass

# ==============================================================================
# DIVISÃO E NORMALIZAÇÃO
# ==============================================================================

X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED)
X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.2, random_state=SEED)

print(f"\n✂️  Divisão:")
print(f"   Treino:    {len(X_train):,}")
print(f"   Validação: {len(X_val):,}")
print(f"   Teste:     {len(X_test):,}")

scaler_X = StandardScaler()
scaler_y = StandardScaler()

X_train_sc = scaler_X.fit_transform(X_train)
X_val_sc   = scaler_X.transform(X_val)
X_test_sc  = scaler_X.transform(X_test)

y_train_sc = scaler_y.fit_transform(y_train)
y_val_sc   = scaler_y.transform(y_val)
y_test_sc  = scaler_y.transform(y_test)

n_inputs  = X_train.shape[1]
n_outputs = y_train.shape[1]

# ==============================================================================
# 🏗️ TREINAMENTO MODELO BASE
# ==============================================================================

print(f"\n" + "="*80)
print("TREINAMENTO MODELO BASE")
print("="*80)

indices_criticos = [i for i, nome in enumerate(outputs_detectados)
                    if nome in variaveis_criticas_encontradas]

print(f"\n🔄 Criando modelo MLP...")
model_base = build_simple_model(n_inputs, n_outputs, LR_BASE)
print(f"   Inputs:     {n_inputs}")
print(f"   Outputs:    {n_outputs}")
print(f"   Parâmetros: {model_base.count_params():,}")

early_stop = callbacks.EarlyStopping(
    monitor='val_loss', patience=PATIENCE_BASE,
    restore_best_weights=True, verbose=0)

reduce_lr = callbacks.ReduceLROnPlateau(
    monitor='val_loss', factor=0.5, patience=20,
    min_lr=1e-7, verbose=0)

print(f"\n🚀 Treinando modelo base...")
history_base = model_base.fit(
    X_train_sc, y_train_sc,
    validation_data=(X_val_sc, y_val_sc),
    epochs=EPOCHS_BASE,
    batch_size=BATCH_SIZE_BASE,
    callbacks=[early_stop, reduce_lr],
    verbose=1
)

epocas_treinadas = len(history_base.history['loss'])
print(f"   ✅ Concluído em {epocas_treinadas} épocas")

# ──────────────────────────────────────────────────────────────────────────────
# 💾 SALVAR HISTORY DO MODELO BASE
# ──────────────────────────────────────────────────────────────────────────────
pasta = Path(MODELO_PATH)
pasta.mkdir(exist_ok=True)

history_path = pasta / 'history_base.json'
with open(history_path, 'w', encoding='utf-8') as f:
    json.dump({k: [float(v) for v in vals]
               for k, vals in history_base.history.items()}, f)
print(f"   ✅ History salvo: {history_path.name}")

# Avaliar modelo base
y_pred_test_sc = model_base.predict(X_test_sc, verbose=0)
y_pred_test    = scaler_y.inverse_transform(y_pred_test_sc)
y_pred_test    = inverter_transformacao_seletiva(y_pred_test, INDICES_TRANSFORMADOS)

r2_por_output    = np.array([r2_score(y_test[:, i], y_pred_test[:, i])   for i in range(n_outputs)])
rmse_por_output  = np.array([np.sqrt(mean_squared_error(y_test[:, i], y_pred_test[:, i])) for i in range(n_outputs)])
mae_por_output   = np.array([mean_absolute_error(y_test[:, i], y_pred_test[:, i])          for i in range(n_outputs)])
smape_por_output = np.array([smape_vec(y_test[:, i], y_pred_test[:, i])  for i in range(n_outputs)])

print(f"\n📊 R² médio inicial: {r2_por_output.mean():.4f}")

# Diagnóstico da variável crítica
target_name = 'PRODUTO_ACETA-01_MOLEFRAC_MIXED'
if target_name in outputs_detectados:
    idx_target = outputs_detectados.index(target_name)
    print(f"\n{'█'*80}")
    print(f"🔎 DIAGNÓSTICO PRÉ-RETREINO: {target_name}")
    print(f"   R² ATUAL: {r2_por_output[idx_target]:.6f}")
    print('█'*80)

# ==============================================================================
# 🎯 IDENTIFICAR OUTPUTS PARA RETREINAMENTO E REMOÇÃO
# ==============================================================================

print(f"\n" + "="*80)
print("ANÁLISE E ESTRATÉGIA DE RETREINAMENTO")
print("="*80)

outputs_irrecuperaveis = []
if REMOVER_OUTPUTS_RUINS:
    for i, output_name in enumerate(outputs_detectados):
        r2_atual   = r2_por_output[i]
        eh_critica = output_name in variaveis_criticas_encontradas

        if r2_atual < LIMITE_R2_MINIMO and not eh_critica:
            outputs_irrecuperaveis.append({'indice': i, 'nome': output_name, 'r2': r2_atual})
        elif eh_critica and r2_atual < LIMITE_R2_MINIMO:
            print(f"   ⚠️  PROTEGIDA: {output_name} (R²={r2_atual:.4f})")

    if outputs_irrecuperaveis:
        print(f"\n🗑️  OUTPUTS IRRECUPERÁVEIS (R² < {LIMITE_R2_MINIMO}):")
        for o in outputs_irrecuperaveis[:10]:
            print(f"   • {o['nome'][:60]:<60} | R²={o['r2']:.4f}")
        if len(outputs_irrecuperaveis) > 10:
            print(f"   ... e mais {len(outputs_irrecuperaveis)-10}")

        indices_manter = [i for i in range(n_outputs)
                          if i not in [o['indice'] for o in outputs_irrecuperaveis]]

        y_train     = y_train[:, indices_manter]
        y_val       = y_val[:, indices_manter]
        y_test      = y_test[:, indices_manter]
        y_pred_test = y_pred_test[:, indices_manter]

        nomes_transformados    = [outputs_detectados[i] for i in INDICES_TRANSFORMADOS]
        outputs_detectados     = [outputs_detectados[i] for i in indices_manter]
        INDICES_TRANSFORMADOS  = [i for i, nome in enumerate(outputs_detectados)
                                  if nome in nomes_transformados]

        r2_por_output    = r2_por_output[indices_manter]
        rmse_por_output  = rmse_por_output[indices_manter]
        mae_por_output   = mae_por_output[indices_manter]
        smape_por_output = smape_por_output[indices_manter]

        variaveis_criticas_encontradas = [v for v in variaveis_criticas_encontradas
                                          if v in outputs_detectados]
        n_outputs = len(outputs_detectados)

        print(f"\n✅ Outputs restantes: {n_outputs}")

        scaler_y   = StandardScaler()
        y_train_sc = scaler_y.fit_transform(y_train)
        y_val_sc   = scaler_y.transform(y_val)
        y_test_sc  = scaler_y.transform(y_test)

        print(f"\n🔄 Retreinando modelo BASE com outputs filtrados...")
        model_base = build_simple_model(n_inputs, n_outputs, LR_BASE)
        history_base = model_base.fit(
            X_train_sc, y_train_sc,
            validation_data=(X_val_sc, y_val_sc),
            epochs=EPOCHS_BASE,
            batch_size=BATCH_SIZE_BASE,
            callbacks=[early_stop, reduce_lr],
            verbose=1
        )

        epocas_treinadas = len(history_base.history['loss'])

        # ── Atualizar history salvo após retreino ──────────────────────────────
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump({k: [float(v) for v in vals]
                       for k, vals in history_base.history.items()}, f)
        print(f"   ✅ History atualizado após remoção de outputs ruins")

        y_pred_test_sc = model_base.predict(X_test_sc, verbose=0)
        y_pred_test    = scaler_y.inverse_transform(y_pred_test_sc)
        y_pred_test    = inverter_transformacao_seletiva(y_pred_test, INDICES_TRANSFORMADOS)

        r2_por_output    = np.array([r2_score(y_test[:, i], y_pred_test[:, i])   for i in range(n_outputs)])
        rmse_por_output  = np.array([np.sqrt(mean_squared_error(y_test[:, i], y_pred_test[:, i])) for i in range(n_outputs)])
        mae_por_output   = np.array([mean_absolute_error(y_test[:, i], y_pred_test[:, i])          for i in range(n_outputs)])
        smape_por_output = np.array([smape_vec(y_test[:, i], y_pred_test[:, i])  for i in range(n_outputs)])

        print(f"   ✅ Novo R² médio: {r2_por_output.mean():.4f}")

# Identificar outputs para retreinamento
outputs_para_retreinar = []
for i, output_name in enumerate(outputs_detectados):
    r2_atual   = r2_por_output[i]
    eh_critica = output_name in variaveis_criticas_encontradas

    if eh_critica and r2_atual < LIMITE_R2_CRITICO:
        outputs_para_retreinar.append({
            'indice': i, 'nome': output_name, 'r2_atual': r2_atual,
            'alvo': LIMITE_R2_CRITICO, 'critica': True,
            'max_tentativas': MAX_TENTATIVAS_CRITICAS
        })
    elif not eh_critica and r2_atual < LIMITE_R2_NORMAL:
        outputs_para_retreinar.append({
            'indice': i, 'nome': output_name, 'r2_atual': r2_atual,
            'alvo': LIMITE_R2_NORMAL, 'critica': False,
            'max_tentativas': MAX_TENTATIVAS_RETREINO
        })

print(f"\n📋 Outputs para retreinamento: {len(outputs_para_retreinar)}")

# ==============================================================================
# 🔄 RETREINAMENTO ESPECIALIZADO
# ==============================================================================

MAX_TENTATIVAS_TARGET = cfg['training']['retraining']['max_attempts_critical']
r2_critical           = cfg['thresholds']['r2_critical']
historico_retreinos   = []

TREINAR_ESPECIALISTAS = False  # ← mude para True para ativar especialistas

if TREINAR_ESPECIALISTAS and outputs_para_retreinar:
    print(f"\n🔄 Iniciando retreinamentos especializados...")

    outputs_sorted = sorted(outputs_para_retreinar,
                            key=lambda x: (not x['critica'], x['r2_atual']))

    for idx_ret, output_info in enumerate(outputs_sorted, 1):
        indice_output = output_info['indice']
        nome_output   = output_info['nome']
        r2_inicial    = output_info['r2_atual']
        alvo_r2       = output_info['alvo']
        critica       = output_info['critica']
        max_tent      = output_info['max_tentativas']

        print(f"\n{'='*80}")
        print(f"Retreinamento {idx_ret}/{len(outputs_sorted)}: {nome_output}")
        print(f"   R² atual: {r2_inicial:.4f} → alvo: {alvo_r2}")

        melhor_r2       = r2_inicial
        melhor_modelo   = None
        melhor_scaler   = None
        melhor_tentativa = 0

        for tentativa in range(1, max_tent + 1):
            lrs_criticas = [0.0005, 0.0003, 0.0001, 0.00005, 0.00003]
            if critica:
                lr_atual     = lrs_criticas[min(tentativa-1, len(lrs_criticas)-1)]
                epochs_atual = EPOCHS_BASE + (150 * tentativa)
            else:
                lr_atual     = LR_BASE * (AJUSTE_LR_RETREINO ** (tentativa - 1))
                epochs_atual = EPOCHS_BASE + (AUMENTO_EPOCHS_RETREINO * tentativa)

            y_train_esp = y_train[:, [indice_output]]
            y_val_esp   = y_val[:,   [indice_output]]
            y_test_esp  = y_test[:,  [indice_output]]

            sc_esp          = StandardScaler()
            y_train_esp_sc  = sc_esp.fit_transform(y_train_esp)
            y_val_esp_sc    = sc_esp.transform(y_val_esp)

            model_esp = criar_modelo_especializado(n_inputs, 1, lr_atual)
            patience_atual = PATIENCE_BASE * 2 if critica else PATIENCE_BASE

            model_esp.fit(
                X_train_sc, y_train_esp_sc,
                validation_data=(X_val_sc, y_val_esp_sc),
                epochs=epochs_atual,
                batch_size=BATCH_SIZE_BASE,
                callbacks=[
                    callbacks.EarlyStopping(monitor='val_loss', patience=patience_atual,
                                            restore_best_weights=True, verbose=0),
                    callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5,
                                               patience=patience_atual//2, min_lr=1e-7, verbose=0)
                ],
                verbose=0
            )

            y_pred_esp = sc_esp.inverse_transform(model_esp.predict(X_test_sc, verbose=0))
            r2_esp     = r2_score(y_test_esp, y_pred_esp)

            print(f"   Tentativa {tentativa}: R²={r2_esp:.4f} (LR={lr_atual:.6f})")

            if r2_esp > melhor_r2:
                melhor_r2        = r2_esp
                melhor_modelo    = model_esp
                melhor_scaler    = sc_esp
                melhor_tentativa = tentativa

            if melhor_r2 >= 0.99 or (melhor_r2 >= alvo_r2 + 0.01 and tentativa > 3):
                break

        MELHORIA_MINIMA = 0.005
        if melhor_r2 > r2_inicial + MELHORIA_MINIMA:
            nome_arq_modelo = f"especialista_{indice_output}_{nome_output.replace('/', '_')}.keras"
            nome_arq_scaler = f"scaler_{indice_output}.pkl"

            melhor_modelo.save(ESPECIALISTAS_PATH / nome_arq_modelo)
            joblib.dump(melhor_scaler, ESPECIALISTAS_PATH / nome_arq_scaler)

            y_pred_melhor = melhor_scaler.inverse_transform(
                melhor_modelo.predict(X_test_sc, verbose=0))
            y_pred_test[:, indice_output] = y_pred_melhor.flatten()
            r2_por_output[indice_output]  = melhor_r2

            historico_retreinos.append({
                'output': nome_output, 'indice': indice_output,
                'critica': critica,
                'r2_inicial': r2_inicial, 'r2_final': melhor_r2,
                'melhoria': melhor_r2 - r2_inicial,
                'tentativas': melhor_tentativa,
                'atingiu_alvo': melhor_r2 >= alvo_r2,
                'caminho_modelo': nome_arq_modelo,
                'caminho_scaler': nome_arq_scaler
            })
            print(f"   ✅ Salvo: R² {r2_inicial:.4f} → {melhor_r2:.4f}")
        else:
            print(f"   ❌ Melhoria insuficiente após {max_tent} tentativas")

# ==============================================================================
# 📊 AVALIAÇÃO FINAL
# ==============================================================================

print(f"\n" + "="*80)
print("AVALIAÇÃO FINAL")
print("="*80)

r2_por_output_final = np.array([r2_score(y_test[:, i], y_pred_test[:, i])
                                 for i in range(n_outputs)])

outputs_criticos_aprovados = outputs_criticos_total = 0
outputs_normais_aprovados  = outputs_normais_total  = 0

for i, nome in enumerate(outputs_detectados):
    r2 = r2_por_output_final[i]
    if nome in variaveis_criticas_encontradas:
        outputs_criticos_total += 1
        if r2 >= LIMITE_R2_CRITICO:
            outputs_criticos_aprovados += 1
    else:
        outputs_normais_total += 1
        if r2 >= LIMITE_R2_NORMAL:
            outputs_normais_aprovados += 1

outputs_total_aprovados = outputs_criticos_aprovados + outputs_normais_aprovados
taxa_aprovacao_geral    = (outputs_total_aprovados / n_outputs) * 100

print(f"\n🎯 RESULTADOS:")
print(f"   Críticas:  {outputs_criticos_aprovados}/{outputs_criticos_total}")
print(f"   Normais:   {outputs_normais_aprovados}/{outputs_normais_total}")
print(f"   Geral:     {outputs_total_aprovados}/{n_outputs} ({taxa_aprovacao_geral:.1f}%) — meta: {PERCENTUAL_APROVACAO}%")
print(f"\n📈 R²: média={r2_por_output_final.mean():.4f} | "
      f"mediana={np.median(r2_por_output_final):.4f} | "
      f"min={r2_por_output_final.min():.4f} | max={r2_por_output_final.max():.4f}")

# ==============================================================================
# 💾 SALVAR MODELO, SCALERS, CONFIG E CSV
# ==============================================================================

print(f"\n" + "="*80)
print("SALVANDO RESULTADOS")
print("="*80)

model_base.save(pasta / 'modelo_base.keras')
joblib.dump(scaler_X, pasta / 'scaler_X.pkl')
joblib.dump(scaler_y, pasta / 'scaler_y.pkl')
print(f"\n✅ Modelo base e scalers salvos")

# Config final
outputs_detalhados = []
for i, nome in enumerate(outputs_detectados):
    eh_critica = nome in variaveis_criticas_encontradas
    r2         = float(r2_por_output_final[i])
    alvo       = LIMITE_R2_CRITICO if eh_critica else LIMITE_R2_NORMAL
    info_ret   = next((
        {'foi_retreinado': True, 'r2_inicial': float(h['r2_inicial']),
         'r2_final': float(h['r2_final']), 'melhoria': float(h['melhoria']),
         'tentativas': int(h['tentativas']), 'atingiu_alvo': bool(h['atingiu_alvo']),
         'caminho_modelo': h['caminho_modelo'], 'caminho_scaler': h['caminho_scaler']}
        for h in historico_retreinos if h['indice'] == i
    ), {'foi_retreinado': False})

    outputs_detalhados.append({
        'indice': i, 'nome': nome, 'critica': eh_critica,
        'r2': r2, 'r2_alvo': alvo, 'aprovado': r2 >= alvo,
        'rmse': float(rmse_por_output[i]),
        'mae':  float(mae_por_output[i]),
        'smape': float(smape_por_output[i]),
        'retreinamento': info_ret
    })

config_final = {
    'timestamp':            pd.Timestamp.now().isoformat(),
    'arquitetura_tipo':     'MLP_Simple',
    'transformacao_target': USA_TRANSFORM,
    'indices_transformados': INDICES_TRANSFORMADOS,
    'dataset': {
        'caminho':  str(DATASET_PATH),
        'total_linhas': len(df_clean),
        'extremos_removidos':         REMOVER_DATASET_EXTREMOS,
        'filtro_qualidade_aplicado':  APLICAR_FILTRO_QUALIDADE,
        'divisao': {'treino': len(X_train), 'validacao': len(X_val), 'teste': len(X_test)}
    },
    'outputs_removidos': {
        'total':    len(outputs_irrecuperaveis) if 'outputs_irrecuperaveis' in locals() else 0,
        'criterio': f'R² < {LIMITE_R2_MINIMO}',
        'lista':    [o['nome'] for o in outputs_irrecuperaveis] if 'outputs_irrecuperaveis' in locals() else []
    },
    'modelo': {
        'tipo':               'MLP Simples',
        'parametros_total':   int(model_base.count_params()),
        'learning_rate':      LR_BASE,
        'batch_size':         BATCH_SIZE_BASE,
        'epocas_treinadas':   epocas_treinadas,
        'n_inputs':           n_inputs,
        'n_outputs':          n_outputs,
        'optimizer':          'Adamax'
    },
    'criterios': {
        'r2_criticas':              LIMITE_R2_CRITICO,
        'r2_normais':               LIMITE_R2_NORMAL,
        'r2_minimo':                LIMITE_R2_MINIMO,
        'percentual_aprovacao_meta': PERCENTUAL_APROVACAO,
        'max_tentativas_normais':   MAX_TENTATIVAS_RETREINO,
        'max_tentativas_criticas':  MAX_TENTATIVAS_CRITICAS
    },
    'variaveis_criticas_configuradas':  VARIAVEIS_CRITICAS,
    'variaveis_criticas_encontradas':   variaveis_criticas_encontradas,
    'variaveis_criticas_nao_encontradas': variaveis_criticas_nao_encontradas,
    'resultados_globais': {
        'r2_medio':   float(r2_por_output_final.mean()),
        'r2_mediano': float(np.median(r2_por_output_final)),
        'r2_minimo':  float(r2_por_output_final.min()),
        'r2_maximo':  float(r2_por_output_final.max()),
        'rmse_medio': float(rmse_por_output.mean()),
        'mae_medio':  float(mae_por_output.mean()),
        'smape_medio': float(smape_por_output.mean())
    },
    'aprovacao': {
        'criticas': {
            'total': outputs_criticos_total, 'aprovadas': outputs_criticos_aprovados,
            'taxa_pct': float(outputs_criticos_aprovados / outputs_criticos_total * 100) if outputs_criticos_total > 0 else 0.0
        },
        'normais': {
            'total': outputs_normais_total, 'aprovadas': outputs_normais_aprovados,
            'taxa_pct': float(outputs_normais_aprovados / outputs_normais_total * 100) if outputs_normais_total > 0 else 0.0
        },
        'geral': {
            'total': n_outputs, 'aprovadas': outputs_total_aprovados,
            'taxa_pct': float(taxa_aprovacao_geral),
            'meta_atingida': taxa_aprovacao_geral >= PERCENTUAL_APROVACAO
        }
    },
    'retreinamentos': {
        'total_outputs_retreinados': len(historico_retreinos),
        'melhoria_media': float(np.mean([h['melhoria'] for h in historico_retreinos])) if historico_retreinos else 0.0,
        'alvos_atingidos': sum(1 for h in historico_retreinos if h['atingiu_alvo']),
        'historico': historico_retreinos
    },
    'outputs_individuais': outputs_detalhados,
    'inputs': inputs_detectados,
    'pastas': {
        'modelos':        str(MODELO_PATH),
        'especialistas':  str(ESPECIALISTAS_PATH),
        'visualizacoes':  str(OUTPUT_PATH)
    }
}

with open(pasta / 'config_final.json', 'w', encoding='utf-8') as f:
    json.dump(config_final, f, indent=2, ensure_ascii=False)
print(f"✅ config_final.json salvo")

df_r2_individual = pd.DataFrame({
    'output':  outputs_detectados,
    'critica': [n in variaveis_criticas_encontradas for n in outputs_detectados],
    'r2':      r2_por_output_final,
    'r2_alvo': [LIMITE_R2_CRITICO if n in variaveis_criticas_encontradas else LIMITE_R2_NORMAL
                for n in outputs_detectados],
    'aprovado': [r2 >= (LIMITE_R2_CRITICO if n in variaveis_criticas_encontradas else LIMITE_R2_NORMAL)
                 for n, r2 in zip(outputs_detectados, r2_por_output_final)],
    'rmse':  rmse_por_output,
    'mae':   mae_por_output,
    'smape': smape_por_output,
    'tem_especialista': [any(h['indice'] == i for h in historico_retreinos) for i in range(n_outputs)]
}).sort_values('r2', ascending=False)

df_r2_individual.to_csv(pasta / 'r2_individual_por_output.csv', index=False)
print(f"✅ r2_individual_por_output.csv salvo")

# ==============================================================================
# 📊 VISUALIZAÇÕES  ← BLOCO COMPLETO
# ==============================================================================

print(f"\n" + "="*80)
print("GERANDO VISUALIZAÇÕES")
print("="*80)

# ── VIZ 1: Curvas de aprendizado ──────────────────────────────────────────────
print(f"\n   📈 Curvas de aprendizado...")

fig, axes = plt.subplots(1, 2, figsize=(16, 5))
epocas = range(1, epocas_treinadas + 1)

axes[0].plot(epocas, history_base.history['loss'],     color='steelblue', lw=2, label='Train Loss')
axes[0].plot(epocas, history_base.history['val_loss'], color='orange',    lw=2, label='Val Loss')
axes[0].set_xlabel('Época', fontsize=12)
axes[0].set_ylabel('Loss (MSE)', fontsize=12)
axes[0].set_title('Curva de Aprendizado — Loss', fontsize=13, fontweight='bold')
axes[0].legend(fontsize=11)
axes[0].grid(True, alpha=0.3)

axes[1].plot(epocas, history_base.history['mae'],     color='steelblue', lw=2, label='Train MAE')
axes[1].plot(epocas, history_base.history['val_mae'], color='orange',    lw=2, label='Val MAE')
axes[1].set_xlabel('Época', fontsize=12)
axes[1].set_ylabel('MAE', fontsize=12)
axes[1].set_title('Curva de Aprendizado — MAE', fontsize=13, fontweight='bold')
axes[1].legend(fontsize=11)
axes[1].grid(True, alpha=0.3)

plt.suptitle(f"Treinamento Modelo Base — {epocas_treinadas} épocas", fontsize=14, fontweight='bold')
plt.tight_layout()
p = os.path.join(OUTPUT_PATH, '02_curvas_aprendizado.png')
plt.savefig(p, dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ Salvo: 02_curvas_aprendizado.png")

# ── VIZ 2: Distribuição R² + R² por output + Top piores/melhores ──────────────
print(f"\n   📊 Distribuição R² e ranking de outputs...")

fig = plt.figure(figsize=(22, 14))
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.3)

# Histograma
ax1 = fig.add_subplot(gs[0, 0])
ax1.hist(r2_por_output_final, bins=30, color='steelblue', edgecolor='white', alpha=0.85)
ax1.axvline(r2_por_output_final.mean(),     color='red',    linestyle='--', lw=2,
            label=f'Média: {r2_por_output_final.mean():.3f}')
ax1.axvline(np.median(r2_por_output_final), color='green',  linestyle='--', lw=2,
            label=f'Mediana: {np.median(r2_por_output_final):.3f}')
ax1.axvline(LIMITE_R2_NORMAL, color='orange', linestyle=':', lw=1.5,
            label=f'Limiar: {LIMITE_R2_NORMAL}')
ax1.set_xlabel('R² Score', fontsize=12)
ax1.set_ylabel('Frequência', fontsize=12)
ax1.set_title('Distribuição de R²', fontsize=13, fontweight='bold')
ax1.legend(fontsize=10)
ax1.grid(True, alpha=0.3)

# R² por output ordenado
ax2 = fig.add_subplot(gs[0, 1])
r2_sorted  = np.sort(r2_por_output_final)
cores_bar  = ['green' if v >= LIMITE_R2_NORMAL else
               ('orange' if v >= LIMITE_R2_MINIMO else 'red') for v in r2_sorted]
ax2.bar(range(len(r2_sorted)), r2_sorted, color=cores_bar, alpha=0.75, width=1.0)
ax2.axhline(r2_por_output_final.mean(), color='gold',   linestyle='--', lw=2,
            label=f'Média: {r2_por_output_final.mean():.3f}')
ax2.axhline(LIMITE_R2_NORMAL, color='orange', linestyle='--', lw=1.5, alpha=0.7)
legend_els = [Patch(facecolor='green',  label=f'>= {LIMITE_R2_NORMAL}'),
              Patch(facecolor='orange', label=f'>= {LIMITE_R2_MINIMO}'),
              Patch(facecolor='red',    label=f'< {LIMITE_R2_MINIMO}')]
ax2.legend(handles=legend_els, fontsize=9, loc='upper left')
ax2.set_xlabel('Output (ordenado do pior para melhor)', fontsize=12)
ax2.set_ylabel('R² Score', fontsize=12)
ax2.set_title('R² por Output', fontsize=13, fontweight='bold')
ax2.grid(True, alpha=0.3, axis='y')

N_TOP = 15
df_r2_viz      = pd.DataFrame({'output': outputs_detectados, 'r2': r2_por_output_final})
df_piores_viz  = df_r2_viz.nsmallest(N_TOP, 'r2')
df_melhores_viz = df_r2_viz.nlargest(N_TOP, 'r2')

# Top piores
ax3 = fig.add_subplot(gs[1, 0])
cores_p = ['red' if v < LIMITE_R2_MINIMO else 'orange' for v in df_piores_viz['r2']]
ax3.barh(range(len(df_piores_viz)), df_piores_viz['r2'], color=cores_p, alpha=0.8)
ax3.set_yticks(range(len(df_piores_viz)))
ax3.set_yticklabels([n[:42] for n in df_piores_viz['output']], fontsize=9)
for i, (_, row) in enumerate(df_piores_viz.iterrows()):
    ax3.text(max(row['r2'] + 0.01, 0.01), i, f"{row['r2']:.3f}",
             va='center', fontsize=8, fontweight='bold')
ax3.set_xlabel('R² Score', fontsize=12)
ax3.set_title(f'Top {N_TOP} Piores Outputs', fontsize=13, fontweight='bold', color='red')
ax3.axvline(LIMITE_R2_MINIMO, color='red', linestyle='--', lw=1.5, alpha=0.7)
ax3.grid(True, alpha=0.3, axis='x')

# Top melhores
ax4 = fig.add_subplot(gs[1, 1])
cores_m = ['darkgreen' if v >= LIMITE_R2_CRITICO else 'green' for v in df_melhores_viz['r2']]
ax4.barh(range(len(df_melhores_viz)), df_melhores_viz['r2'], color=cores_m, alpha=0.8)
ax4.set_yticks(range(len(df_melhores_viz)))
ax4.set_yticklabels([n[:42] for n in df_melhores_viz['output']], fontsize=9)
for i, (_, row) in enumerate(df_melhores_viz.iterrows()):
    ax4.text(row['r2'] - 0.04, i, f"{row['r2']:.4f}",
             va='center', fontsize=8, fontweight='bold', color='white')
ax4.set_xlabel('R² Score', fontsize=12)
ax4.set_title(f'Top {N_TOP} Melhores Outputs', fontsize=13, fontweight='bold', color='darkgreen')
ax4.set_xlim(0, 1.05)
ax4.axvline(LIMITE_R2_NORMAL, color='orange', linestyle='--', lw=1.5, alpha=0.7)
ax4.grid(True, alpha=0.3, axis='x')

# Marcar variáveis críticas em vermelho nos yticks
for ax_chk, df_chk in [(ax3, df_piores_viz), (ax4, df_melhores_viz)]:
    labels = ax_chk.get_yticklabels()
    for lbl, (_, row) in zip(labels, df_chk.iterrows()):
        if row['output'] in VARIAVEIS_CRITICAS:
            lbl.set_color('red')
            lbl.set_fontweight('bold')

plt.suptitle(
    f"Análise de R² — {n_outputs} outputs | "
    f"Aprovados: {outputs_total_aprovados}/{n_outputs} ({taxa_aprovacao_geral:.1f}%)",
    fontsize=14, fontweight='bold')
p = os.path.join(OUTPUT_PATH, '03_r2_distribuicao_ranking.png')
plt.savefig(p, dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ Salvo: 03_r2_distribuicao_ranking.png")

# ── VIZ 3: Comparação MLP vs Linear vs Ridge ─────────────────────────────────
print(f"\n   🔄 Comparação com modelos lineares (treinando Linear e Ridge)...")

scaler_X_lin = StandardScaler()
X_train_lin  = scaler_X_lin.fit_transform(X_train)
X_test_lin   = scaler_X_lin.transform(X_test)

r2_linear = np.zeros(n_outputs)
r2_ridge  = np.zeros(n_outputs)

for i in range(n_outputs):
    lr_lin = LinearRegression()
    lr_lin.fit(X_train_lin, y_train[:, i])
    r2_linear[i] = r2_score(y_test[:, i], lr_lin.predict(X_test_lin))

    rr = Ridge(alpha=1.0)
    rr.fit(X_train_lin, y_train[:, i])
    r2_ridge[i] = r2_score(y_test[:, i], rr.predict(X_test_lin))

    if (i + 1) % 50 == 0 or i == n_outputs - 1:
        print(f"      Output {i+1}/{n_outputs}...", end='\r')

print(f"\n   Linear R² médio: {r2_linear.mean():.4f}")
print(f"   Ridge  R² médio: {r2_ridge.mean():.4f}")
print(f"   MLP    R² médio: {r2_por_output_final.mean():.4f}")

fig, axes = plt.subplots(1, 2, figsize=(16, 7))
lim = [-0.15, 1.05]

for ax, r2_base, nome, cor in [
    (axes[0], r2_linear, 'Linear Regression', 'steelblue'),
    (axes[1], r2_ridge,  'Ridge Regression',   'darkorange')
]:
    ax.scatter(r2_base, r2_por_output_final, alpha=0.5, s=25, color=cor, edgecolors='none')
    ax.plot(lim, lim, 'r--', lw=2, label='y=x (empate)')
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel(f'R² {nome}', fontsize=12)
    ax.set_ylabel('R² MLP (Keras)', fontsize=12)
    ax.set_title(f'MLP vs {nome}\n(pontos acima = MLP melhor)', fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    ganho = (r2_por_output_final > r2_base).sum()
    ax.text(0.04, 0.92,
            f"MLP melhor em {ganho}/{n_outputs} ({ganho/n_outputs*100:.1f}%)",
            transform=ax.transAxes, fontsize=10,
            bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))

plt.suptitle(
    f"Comparação: MLP vs Modelos Lineares\n"
    f"Linear: {r2_linear.mean():.4f} | Ridge: {r2_ridge.mean():.4f} | MLP: {r2_por_output_final.mean():.4f}",
    fontsize=13, fontweight='bold')
plt.tight_layout()
p = os.path.join(OUTPUT_PATH, '04_comparacao_linear_vs_mlp.png')
plt.savefig(p, dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ Salvo: 04_comparacao_linear_vs_mlp.png")

# ── VIZ 4: Arquitetura do sistema (resumo) ────────────────────────────────────
print(f"\n   🏗️  Arquitetura do sistema...")

fig, ax = plt.subplots(figsize=(14, 8))
ax.text(0.5, 0.93, 'SISTEMA: MODELO BASE + ESPECIALISTAS',
        ha='center', fontsize=16, fontweight='bold', transform=ax.transAxes)

ax.add_patch(plt.Rectangle((0.1, 0.55), 0.35, 0.22,
             fill=True, facecolor='lightblue', edgecolor='black', linewidth=2, transform=ax.transAxes))
ax.text(0.275, 0.66,
        f'MODELO BASE\nMLP Simples\n{model_base.count_params():,} parâmetros',
        ha='center', va='center', fontsize=11, fontweight='bold', transform=ax.transAxes)

ax.add_patch(plt.Rectangle((0.55, 0.55), 0.35, 0.22,
             fill=True, facecolor='lightcoral', edgecolor='black', linewidth=2, transform=ax.transAxes))
ax.text(0.725, 0.66,
        f'ESPECIALISTAS\n{len(historico_retreinos)} modelos\nAlta precisão',
        ha='center', va='center', fontsize=11, fontweight='bold', transform=ax.transAxes)

ax.annotate('', xy=(0.275, 0.35), xytext=(0.275, 0.55),
            xycoords='axes fraction', textcoords='axes fraction',
            arrowprops=dict(arrowstyle='->', color='blue', lw=2))
ax.annotate('', xy=(0.725, 0.35), xytext=(0.725, 0.55),
            xycoords='axes fraction', textcoords='axes fraction',
            arrowprops=dict(arrowstyle='->', color='red', lw=2))

ax.add_patch(plt.Rectangle((0.25, 0.13), 0.5, 0.22,
             fill=True, facecolor='lightgreen', edgecolor='black', linewidth=2, transform=ax.transAxes))
ax.text(0.5, 0.24,
        f'PREDIÇÃO FINAL\n{outputs_total_aprovados}/{n_outputs} aprovados ({taxa_aprovacao_geral:.1f}%)\n'
        f'R² médio: {r2_por_output_final.mean():.4f}',
        ha='center', va='center', fontsize=12, fontweight='bold', transform=ax.transAxes)

ax.axis('off')
p = os.path.join(OUTPUT_PATH, '00_arquitetura_sistema.png')
plt.savefig(p, dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ Salvo: 00_arquitetura_sistema.png")

# ── VIZ 5: R² sistema híbrido ─────────────────────────────────────────────────
print(f"\n   📊 R² sistema híbrido...")

fig, ax = plt.subplots(figsize=(14, max(8, n_outputs * 0.12)))

colors = []
for i, nome in enumerate(outputs_detectados):
    tem_esp = any(h['indice'] == i for h in historico_retreinos)
    r2      = r2_por_output_final[i]
    if tem_esp:
        colors.append('darkgreen' if r2 >= LIMITE_R2_NORMAL else 'orange')
    elif nome in variaveis_criticas_encontradas:
        colors.append('red' if r2 < LIMITE_R2_CRITICO else 'darkgreen')
    else:
        colors.append('orange' if r2 < LIMITE_R2_NORMAL else 'green')

ax.barh(range(n_outputs), r2_por_output_final, color=colors, alpha=0.7)

for i, nome in enumerate(outputs_detectados):
    if any(h['indice'] == i for h in historico_retreinos):
        ax.plot(r2_por_output_final[i], i, 'D', color='gold',
                markersize=10, markeredgecolor='black', markeredgewidth=1.5)

ax.set_yticks(range(n_outputs))
ax.set_yticklabels([n[:50] for n in outputs_detectados], fontsize=7)
ax.set_xlabel('R² Score', fontsize=11)
ax.set_title('R² por Output — Sistema Híbrido\n(♦ = Tem especialista dedicado)',
             fontsize=12, fontweight='bold')
ax.axvline(LIMITE_R2_NORMAL,  color='orange', linestyle='--', alpha=0.7, lw=2)
ax.axvline(LIMITE_R2_CRITICO, color='red',    linestyle='--', alpha=0.7, lw=2)
ax.grid(True, alpha=0.3, axis='x')
ax.invert_yaxis()

p = os.path.join(OUTPUT_PATH, '01_r2_sistema_hibrido.png')
plt.savefig(p, dpi=150, bbox_inches='tight')
plt.close()
print(f"   ✅ Salvo: 01_r2_sistema_hibrido.png")

print(f"\n✅ Todas as visualizações geradas em: {OUTPUT_PATH}")

# ==============================================================================
# 🤖 CLASSE DE INFERÊNCIA
# ==============================================================================

class DigitalTwinPredictor:
    def __init__(self, pasta_modelos):
        self.pasta = Path(pasta_modelos)
        self.model_base  = keras.models.load_model(self.pasta / 'modelo_base.keras', compile=False)
        self.scaler_X    = joblib.load(self.pasta / 'scaler_X.pkl')
        self.scaler_y    = joblib.load(self.pasta / 'scaler_y.pkl')
        with open(self.pasta / 'config_final.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.usa_transform       = self.config.get('transformacao_target', None)
        self.indices_transformados = self.config.get('indices_transformados', [])
        self.especialistas       = {}
        pasta_esp = self.pasta / 'especialistas'
        for h in self.config['retreinamentos']['historico']:
            idx = h['indice']
            cm  = pasta_esp / h['caminho_modelo']
            cs  = pasta_esp / h['caminho_scaler']
            if cm.exists() and cs.exists():
                self.especialistas[idx] = {
                    'model':  keras.models.load_model(cm),
                    'scaler': joblib.load(cs),
                    'nome':   h['output']
                }
        print(f"✅ DigitalTwinPredictor carregado:")
        print(f"   • Base: {self.model_base.count_params():,} parâmetros")
        print(f"   • Especialistas: {len(self.especialistas)}")
        print(f"   • Outputs: {self.config['modelo']['n_outputs']}")

    def predict(self, novos_dados):
        if isinstance(novos_dados, pd.DataFrame):
            novos_dados = novos_dados.values
        X_sc          = self.scaler_X.transform(novos_dados)
        y_pred_sc     = self.model_base.predict(X_sc, verbose=0)
        y_pred_final  = self.scaler_y.inverse_transform(y_pred_sc)
        if self.usa_transform == 'LOGIT_SELETIVO':
            for i in self.indices_transformados:
                y_pred_final[:, i] = 1 / (1 + np.exp(-y_pred_final[:, i]))
        for idx, esp in self.especialistas.items():
            y_esp = esp['scaler'].inverse_transform(esp['model'].predict(X_sc, verbose=0))
            if idx in self.indices_transformados:
                y_esp = 1 / (1 + np.exp(-y_esp))
            y_pred_final[:, idx] = y_esp.flatten()
        return y_pred_final

# Salvar classe
codigo_classe = '''import numpy as np
import pandas as pd
from pathlib import Path
import joblib
import json
import os
from tensorflow import keras

class DigitalTwinPredictor:
    def __init__(self, pasta_modelos):
        self.pasta       = Path(pasta_modelos)
        self.model_base  = keras.models.load_model(self.pasta / "modelo_base.keras", compile=False)
        self.scaler_X    = joblib.load(self.pasta / "scaler_X.pkl")
        self.scaler_y    = joblib.load(self.pasta / "scaler_y.pkl")
        with open(self.pasta / "config_final.json", "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.especialistas = {}
        pasta_esp = self.pasta / "especialistas"
        for h in self.config["retreinamentos"]["historico"]:
            cm = pasta_esp / h["caminho_modelo"]
            cs = pasta_esp / h["caminho_scaler"]
            if cm.exists() and cs.exists():
                self.especialistas[h["indice"]] = {
                    "model":  keras.models.load_model(cm),
                    "scaler": joblib.load(cs),
                    "nome":   h["output"]
                }
        print(f"Predictor carregado: {self.config['modelo']['n_outputs']} outputs, "
              f"{len(self.especialistas)} especialistas")

    def predict(self, novos_dados):
        if isinstance(novos_dados, pd.DataFrame):
            novos_dados = novos_dados.values
        X_sc         = self.scaler_X.transform(novos_dados)
        y_pred       = self.scaler_y.inverse_transform(self.model_base.predict(X_sc, verbose=0))
        for idx, esp in self.especialistas.items():
            y_pred[:, idx] = esp["scaler"].inverse_transform(
                esp["model"].predict(X_sc, verbose=0)).flatten()
        return y_pred
'''
with open(pasta / 'digital_twin_predictor.py', 'w', encoding='utf-8') as f:
    f.write(codigo_classe)
print(f"✅ digital_twin_predictor.py salvo")

# ==============================================================================
# 🧪 TESTE DA CLASSE
# ==============================================================================

try:
    predictor        = DigitalTwinPredictor(MODELO_PATH)
    amostra          = X_test[:5]
    resultado        = predictor.predict(amostra)
    print(f"\n✅ Teste OK — shape saída: {resultado.shape}")
except Exception as e:
    print(f"\n❌ Erro no teste: {e}")

# ==============================================================================
# 📋 RELATÓRIO FINAL
# ==============================================================================

print(f"\n" + "="*80)
print("🎉 TREINAMENTO CONCLUÍDO!")
print("="*80)
print(f"\n📊 RESUMO:")
print(f"   Arquitetura:      MLP Simples ({model_base.count_params():,} parâmetros)")
print(f"   Épocas treinadas: {epocas_treinadas}")
print(f"   R² médio:         {r2_por_output_final.mean():.4f}")
print(f"   Taxa aprovação:   {taxa_aprovacao_geral:.1f}% (meta: {PERCENTUAL_APROVACAO}%)")
print(f"   Status:           {'✅ META ATINGIDA' if taxa_aprovacao_geral >= PERCENTUAL_APROVACAO else '❌ Meta não atingida'}")
print(f"\n📁 ARQUIVOS EM {MODELO_PATH}:")
print(f"   • modelo_base.keras")
print(f"   • scaler_X.pkl / scaler_y.pkl")
print(f"   • config_final.json")
print(f"   • r2_individual_por_output.csv")
print(f"   • history_base.json           ← curvas de aprendizado")
print(f"   • digital_twin_predictor.py")
print(f"\n🖼️  VISUALIZAÇÕES EM {OUTPUT_PATH}:")
print(f"   • 00_arquitetura_sistema.png")
print(f"   • 01_r2_sistema_hibrido.png")
print(f"   • 02_curvas_aprendizado.png   ← Loss e MAE treino/validação")
print(f"   • 03_r2_distribuicao_ranking.png ← histograma + top melhores/piores")
print(f"   • 04_comparacao_linear_vs_mlp.png ← MLP vs Linear vs Ridge")
print(f"\n🚀 USO EM PRODUÇÃO:")
print(f"   from digital_twin_predictor import DigitalTwinPredictor")
print(f"   predictor = DigitalTwinPredictor(r'{MODELO_PATH}')")
print(f"   resultado = predictor.predict(novos_dados)")
print("="*80)