"""
════════════════════════════════════════════════════════════════════════════════
    SISTEMA DE CONTROLE V3 - Orquestrador Completo Integrado
    
    NOVIDADES V3:
    ✅ Integração total com config.yaml
    ✅ Detecção automática da raiz do projeto
    ✅ Thresholds configuráveis
    ✅ Paths relativos automáticos
    ✅ Todas as funcionalidades da V2 mantidas
    ✅ Métricas de drift configuráveis
    ✅ Validação avançada de inputs
════════════════════════════════════════════════════════════════════════════════
"""

import json
import time
import os
import sys
import pandas as pd
import numpy as np
import sqlite3
import logging
import atexit
import signal
import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from sklearn.metrics import mean_absolute_error, r2_score, mean_absolute_percentage_error
import sys
import io
# Força saída UTF-8 no Windows para evitar erro de emojis
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ═══════════════════════════════════════════════════════════════════════════
# DETECÇÃO AUTOMÁTICA DA RAIZ DO PROJETO
# ═══════════════════════════════════════════════════════════════════════════

def encontrar_raiz_projeto():
    """Encontra a raiz do projeto procurando por config.yaml"""
    caminho_atual = Path(__file__).resolve().parent
    
    while caminho_atual != caminho_atual.parent:
        config_path = caminho_atual / "config" / "config.yaml"
        if config_path.exists():
            return caminho_atual
        caminho_atual = caminho_atual.parent
    
    raise FileNotFoundError("❌ config.yaml não encontrado! Verifique a estrutura do projeto.")

RAIZ_PROJETO = encontrar_raiz_projeto()
CONFIG_PATH = RAIZ_PROJETO / "config" / "config.yaml"

# ═══════════════════════════════════════════════════════════════════════════
# CARREGAR CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def carregar_config():
    """Carrega config.yaml e processa paths"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Adicionar defaults se não existirem
    if 'control_system' not in config:
        config['control_system'] = {
            'paths': {
                'controle': 'controle',
                'resultados': 'resultados',
                'historico': 'historico',
                'database': 'historico/digital_twin.db'
            },
            'target_variable': config.get('variables', {}).get('critical', [None])[0],
            'timeouts': {'keras': 10, 'aspen': 60},
            'metrics': {'window_size': 50, 'drift_threshold': 0.15, 'buffer_size': 100},
            'thresholds': {
                'mae_warning': 0.05,
                'mae_critical': 0.10,
                'r2_minimum': 0.85,
                'smape_warning': 10.0,
                'smape_critical': 20.0
            },
            'validation': {'min_nstage': 2, 'enforce_feed_stage_rules': True}
        }
    
    # Processar paths relativos
    paths_ctrl = config['control_system']['paths']
    for key, path in paths_ctrl.items():
        paths_ctrl[key] = str(RAIZ_PROJETO / path)
    
    # Path do modelo
    config['model_path'] = str(RAIZ_PROJETO / config['paths']['output_modelos'])
    
    return config

CONFIG = carregar_config()
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    _cfg_raw = yaml.safe_load(f)

MODO_VALIDACAO = _cfg_raw.get('flags', {}).get('modo_validacao', False)

# Extrair paths
PASTA_CONTROLE = CONFIG['control_system']['paths']['controle']
PASTA_RESULTADOS = CONFIG['control_system']['paths']['resultados']
PASTA_HISTORICO = CONFIG['control_system']['paths']['historico']
DB_PATH = CONFIG['control_system']['paths']['database']
CONFIG_DT_PATH = os.path.join(CONFIG['model_path'], 'config_digital_twin.json')

# Variável target
TARGET_VARIABLE = CONFIG['control_system']['target_variable']
if not TARGET_VARIABLE:
    TARGET_VARIABLE = "PRODUTO_ACETA-01_MOLEFRAC_MIXED"

MODO_VALIDACAO = CONFIG.get('control_system', {}).get('flags', {}).get('modo_validacao', False)
# Criar pastas
os.makedirs(PASTA_CONTROLE, exist_ok=True)
os.makedirs(PASTA_RESULTADOS, exist_ok=True)
os.makedirs(PASTA_HISTORICO, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING ESTRUTURADO
# ═══════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PASTA_HISTORICO, 'sistema_controle_v3.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# FUNÇÃO SMAPE
# ═══════════════════════════════════════════════════════════════════════════

def calcular_smape(y_true, y_pred):
    """
    Calcula SMAPE (Symmetric Mean Absolute Percentage Error)
    SMAPE = 100/n × Σ |y_pred - y_real| / ((|y_pred| + |y_real|) / 2)
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    mask = (np.abs(y_true) > 1e-6) | (np.abs(y_pred) > 1e-6)
    if not np.any(mask):
        return 0.0
    
    y_true_filtered = y_true[mask]
    y_pred_filtered = y_pred[mask]
    
    numerator = np.abs(y_pred_filtered - y_true_filtered)
    denominator = (np.abs(y_pred_filtered) + np.abs(y_true_filtered)) / 2
    denominator = np.where(denominator < 1e-10, 1e-10, denominator)
    
    smape = np.mean(numerator / denominator) * 100
    return smape

# ═══════════════════════════════════════════════════════════════════════════
# BANCO DE DADOS INTEGRADO
# ═══════════════════════════════════════════════════════════════════════════

class DatabaseControle:
    """Banco de dados para orquestração completa"""
    
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._criar_tabelas()
        logger.info(f"BD Controle conectado: {os.path.basename(db_path)}")
    
    def _criar_tabelas(self):
        """Cria tabelas completas"""
        
        # Casos executados
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS casos_executados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                caso_id INTEGER,
                inputs TEXT,
                outputs_keras TEXT,
                outputs_aspen TEXT,
                keras_detectou_risco INTEGER,
                aspen_parou INTEGER,
                tempo_total REAL
            )
        ''')
        
        # Métricas de acurácia
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS metricas_acuracia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                janela_casos INTEGER,
                mae_medio REAL,
                r2_medio REAL,
                mape_medio REAL,
                smape_medio REAL,
                drift_detectado INTEGER,
                variaveis_analisadas TEXT
            )
        ''')
        
        # Buffer para retreinamento
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS buffer_retreino (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                caso_id INTEGER,
                inputs TEXT,
                outputs_reais TEXT
            )
        ''')
        
        # Experimentos
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS experimentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_inicio TEXT,
                timestamp_fim TEXT,
                total_casos INTEGER,
                casos_sucesso INTEGER,
                casos_falha INTEGER,
                taxa_alertas REAL,
                mae_medio REAL,
                r2_medio REAL,
                smape_medio REAL
            )
        ''')
        
        # Alertas de drift
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS alertas_drift (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                metrica TEXT,
                valor REAL,
                threshold REAL,
                severidade TEXT
            )
        ''')
        
        self.conn.commit()
    
    def registrar_caso(self, caso_id, inputs, outputs_keras, outputs_aspen, 
                      keras_risco, aspen_parou, tempo):
        """Registra caso completo"""
        try:
            self.cursor.execute('''
                INSERT INTO casos_executados 
                (timestamp, caso_id, inputs, outputs_keras, outputs_aspen, 
                 keras_detectou_risco, aspen_parou, tempo_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                caso_id,
                json.dumps(inputs),
                json.dumps(outputs_keras),
                json.dumps(outputs_aspen),
                1 if keras_risco else 0,
                1 if aspen_parou else 0,
                tempo
            ))
            self.conn.commit()
            
            # Buffer de retreino
            if outputs_aspen and any(v is not None for v in outputs_aspen.values()):
                self.cursor.execute('''
                    INSERT INTO buffer_retreino (timestamp, caso_id, inputs, outputs_reais)
                    VALUES (?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    caso_id,
                    json.dumps(inputs),
                    json.dumps(outputs_aspen)
                ))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao registrar caso: {e}")
    
    def calcular_metricas_acuracia(self, janela=None):
        """Calcula métricas com detecção de drift"""
        if janela is None:
            janela = CONFIG['control_system']['metrics']['window_size']
        
        try:
            self.cursor.execute('''
                SELECT outputs_keras, outputs_aspen 
                FROM casos_executados 
                WHERE outputs_aspen IS NOT NULL
                ORDER BY id DESC LIMIT ?
            ''', (janela,))
            
            resultados = self.cursor.fetchall()
            if len(resultados) < 10:
                return None
            
            todas_predicoes = []
            todos_reais = []
            variaveis = set()
            
            for keras_json, aspen_json in resultados:
                keras_dict = json.loads(keras_json)
                aspen_dict = json.loads(aspen_json)
                
                for var in keras_dict:
                    if var in aspen_dict and aspen_dict[var] is not None:
                        keras_val = keras_dict[var]
                        aspen_val = aspen_dict[var]
                        
                        if abs(aspen_val) > 1e-6:
                            todas_predicoes.append(keras_val)
                            todos_reais.append(aspen_val)
                            variaveis.add(var)
            
            if len(todas_predicoes) < 10:
                return None
            
            # Calcular métricas
            mae = mean_absolute_error(todos_reais, todas_predicoes)
            r2 = r2_score(todos_reais, todas_predicoes)
            
            # MAPE
            mape_values = []
            for real, pred in zip(todos_reais, todas_predicoes):
                if abs(real) > 1e-3:
                    mape_values.append(abs((real - pred) / real))
            mape = np.mean(mape_values) * 100 if mape_values else 0
            
            # SMAPE
            smape = calcular_smape(todos_reais, todas_predicoes)
            
            # Detecção de drift
            thresholds = CONFIG['control_system']['thresholds']
            drift_detectado = (
                smape > CONFIG['control_system']['metrics']['drift_threshold'] or
                mae > thresholds['mae_critical'] or
                r2 < thresholds['r2_minimum']
            )
            
            # Registrar métricas
            self.cursor.execute('''
                INSERT INTO metricas_acuracia 
                (timestamp, janela_casos, mae_medio, r2_medio, mape_medio, 
                 smape_medio, drift_detectado, variaveis_analisadas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                janela, mae, r2, mape, smape,
                1 if drift_detectado else 0,
                json.dumps(list(variaveis))
            ))
            self.conn.commit()
            
            # Registrar alertas
            if drift_detectado:
                self._registrar_alerta_drift(mae, r2, smape)
            
            return {
                'mae': mae,
                'r2': r2,
                'mape': mape,
                'smape': smape,
                'drift_detectado': drift_detectado,
                'n_variaveis': len(variaveis)
            }
        except Exception as e:
            logger.error(f"Erro ao calcular métricas: {e}")
            return None
    
    def _registrar_alerta_drift(self, mae, r2, smape):
        """Registra alertas de drift"""
        thresholds = CONFIG['control_system']['thresholds']
        
        alertas = []
        if smape > CONFIG['control_system']['metrics']['drift_threshold']:
            alertas.append(('SMAPE', smape, CONFIG['control_system']['metrics']['drift_threshold'], 'CRÍTICO'))
        if mae > thresholds['mae_critical']:
            alertas.append(('MAE', mae, thresholds['mae_critical'], 'CRÍTICO'))
        elif mae > thresholds['mae_warning']:
            alertas.append(('MAE', mae, thresholds['mae_warning'], 'AVISO'))
        if r2 < thresholds['r2_minimum']:
            alertas.append(('R2', r2, thresholds['r2_minimum'], 'CRÍTICO'))
        
        for metrica, valor, threshold, severidade in alertas:
            self.cursor.execute('''
                INSERT INTO alertas_drift (timestamp, metrica, valor, threshold, severidade)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), metrica, valor, threshold, severidade))
        
        self.conn.commit()
    
    def contar_buffer_retreino(self):
        """Conta casos no buffer"""
        try:
            self.cursor.execute('SELECT COUNT(*) FROM buffer_retreino')
            return self.cursor.fetchone()[0]
        except:
            return 0
    
    def limpar_buffer_retreino(self):
        """Limpa buffer"""
        try:
            self.cursor.execute('DELETE FROM buffer_retreino')
            self.conn.commit()
            logger.info("Buffer de retreino limpo")
        except Exception as e:
            logger.error(f"Erro ao limpar buffer: {e}")
    
    def finalizar_experimento(self, timestamp_inicio, total, sucesso, falha, 
                            taxa_alertas, mae, r2, smape):
        """Registra metadados do experimento"""
        try:
            self.cursor.execute('''
                INSERT INTO experimentos 
                (timestamp_inicio, timestamp_fim, total_casos, casos_sucesso, 
                 casos_falha, taxa_alertas, mae_medio, r2_medio, smape_medio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp_inicio, datetime.now().isoformat(),
                total, sucesso, falha, taxa_alertas, mae, r2, smape
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao finalizar experimento: {e}")
    
    def fechar(self):
        """Fecha conexão"""
        self.conn.close()

# ═══════════════════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════

def ler_json_seguro(caminho: str, tentativas: int = 3, delay: float = 0.1) -> Optional[Dict]:
    """Lê JSON com retry"""
    for i in range(tentativas):
        try:
            if not os.path.exists(caminho) or os.path.getsize(caminho) == 0:
                if i < tentativas - 1:
                    time.sleep(delay)
                    continue
                return None
            
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                if not conteudo:
                    if i < tentativas - 1:
                        time.sleep(delay)
                        continue
                    return None
                return json.loads(conteudo)
        except:
            if i < tentativas - 1:
                time.sleep(delay)
    return None

def escrever_json_seguro(caminho: str, dados: Dict) -> bool:
    """Escreve JSON com atomicidade"""
    try:
        caminho_temp = caminho + ".tmp"
        with open(caminho_temp, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        if os.path.exists(caminho):
            os.remove(caminho)
        os.rename(caminho_temp, caminho)
        return True
    except:
        return False

# ═══════════════════════════════════════════════════════════════════════════
# VALIDAÇÃO DE INPUTS
# ═══════════════════════════════════════════════════════════════════════════

def identificar_torres(inputs: List[str]) -> Dict:
    """Identifica pares NSTAGE/FEED_STAGE"""
    torres = {}
    for var in inputs:
        if 'NSTAGE' in var or 'FEED_STAGE' in var or 'FEED' in var:
            torre = var.split('_')[0]
            if torre not in torres:
                torres[torre] = {}
            if 'NSTAGE' in var:
                torres[torre]['nstage'] = var
            elif 'FEED_STAGE' in var or 'FEED' in var:
                torres[torre]['feed'] = var
    return torres

def validar_e_corrigir_inputs(inputs_dict: Dict, torres: Dict) -> Dict:
    """Valida inputs com regras do config"""
    inputs_corrigidos = inputs_dict.copy()
    validation = CONFIG['control_system']['validation']
    
    # Truncar variáveis de estrutura
    for var_name in inputs_corrigidos.keys():
        if any(x in var_name.upper() for x in ['NSTAGE', 'FEED_STAGE', 'STAGE', 'FEED']):
            valor_int = int(round(float(inputs_corrigidos[var_name])))
            if 'NSTAGE' in var_name and valor_int < validation['min_nstage']:
                valor_int = validation['min_nstage']
            inputs_corrigidos[var_name] = valor_int
    
    # Regras de dependência
    if validation['enforce_feed_stage_rules']:
        for torre, info in torres.items():
            if 'nstage' in info and 'feed' in info:
                nstage_var = info['nstage']
                feed_var = info['feed']
                if nstage_var in inputs_corrigidos and feed_var in inputs_corrigidos:
                    nstage = int(inputs_corrigidos[nstage_var])
                    feed = int(inputs_corrigidos[feed_var])
                    if feed < 1:
                        inputs_corrigidos[feed_var] = 1
                        feed = 1
                    if feed >= nstage:
                        inputs_corrigidos[feed_var] = max(1, nstage - 1)
    
    return inputs_corrigidos

# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("SISTEMA DE CONTROLE V3 - DIGITAL TWIN INTEGRADO".center(80))
print("="*80 + "\n")

print(f"📂 Raiz do Projeto: {RAIZ_PROJETO}")
print(f"⚙️  Config: {CONFIG_PATH}")
print(f"🎯 Target: {TARGET_VARIABLE}\n")

# Conectar BD
db = DatabaseControle(DB_PATH)

# Cleanup automático
def cleanup_ao_sair():
    """Executado ao encerrar"""
    try:
        print(f"\n💾 Salvando estado...")
        db.fechar()
        print(f"✅ Banco de dados fechado com segurança")
    except:
        pass

atexit.register(cleanup_ao_sair)

def signal_handler(sig, frame):
    print("\n\n⚠️  Interrompido pelo usuário")
    cleanup_ao_sair()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Buffer de retreino
buffer_count = db.contar_buffer_retreino()
if buffer_count > 0:
    print(f"\n⚠️  Buffer de retreino: {buffer_count} casos")
    resposta = input("Limpar buffer? (s/n): ").strip().lower()
    if resposta == 's':
        db.limpar_buffer_retreino()
        print(f"✅ Buffer limpo!\n")
    else:
        print(f"📝 Buffer mantido\n")

# Carregar config do modelo
try:
    with open(CONFIG_DT_PATH, 'r', encoding='utf-8') as f:
        config_dt = json.load(f)
    
    LIMITE_TARGET = config_dt.get('variaveis_criticas', {}).get('limites', {}).get(TARGET_VARIABLE, {}).get('valor', 0.95)
    print(f"   Limite crítico [{TARGET_VARIABLE}]: {LIMITE_TARGET}\n")
    # Adaptar para estrutura do extrator_sincronizado.py
    # Estrutura esperada: dimensoes.n_inputs, variaveis.inputs, estatisticas_inputs.valores_tipicos
    if 'dimensoes' in config_dt:
        # Estrutura do extrator_sincronizado
        n_inputs = config_dt['dimensoes']['n_inputs']
        n_outputs = config_dt['dimensoes']['n_outputs']
        nomes_inputs = config_dt['variaveis']['inputs']
        nomes_outputs = config_dt['variaveis']['outputs']
        valores_tipicos = config_dt['estatisticas_inputs']['valores_tipicos']
        
        # Criar estrutura flat para compatibilidade
        config_dt['n_inputs'] = n_inputs
        config_dt['n_outputs'] = n_outputs
        config_dt['nomes_inputs'] = nomes_inputs
        config_dt['nomes_outputs'] = nomes_outputs
        config_dt['valores_tipicos'] = valores_tipicos
    else:
        # Estrutura antiga (compatibilidade)
        n_inputs = config_dt.get('n_inputs', len(config_dt.get('nomes_inputs', [])))
        n_outputs = config_dt.get('n_outputs', len(config_dt.get('nomes_outputs', [])))
    
    if n_inputs == 0 or n_outputs == 0:
        print(f"⚠️  Config incompleto!")
        logger.warning("config_digital_twin.json incompleto")
        exit(1)
    
    print(f"✅ Modelo: {n_inputs} inputs, {n_outputs} outputs\n")
    logger.info("Sistema de Controle V3 inicializado")
    
except FileNotFoundError:
    print(f"❌ Arquivo não encontrado: {CONFIG_DT_PATH}")
    print(f"Execute: python scripts/extrator_sincronizado.py")
    logger.error(f"config_digital_twin.json não encontrado")
    exit(1)
except KeyError as e:
    print(f"❌ Chave faltando no config: {e}")
    print(f"Estrutura encontrada: {list(config_dt.keys())}")
    logger.error(f"Chave faltando: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Erro ao carregar config: {e}")
    logger.error(f"Erro ao carregar config_digital_twin.json: {e}")
    exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DOS TESTES
# ═══════════════════════════════════════════════════════════════════════════

print("OPÇÕES DE TESTE:\n")
print("   1. Valores típicos (1 caso)")
print("   2. Variação em torno dos típicos (N casos)")
print("   3. Teste de estresse")
print("   4. Carregar do CSV\n")

opcao = input("Escolha (1-4): ").strip()

casos_teste = []

if opcao == '1':
    casos_teste.append({
        'id': 1,
        'inputs': config_dt['valores_tipicos'].copy(),
        'descricao': 'Valores típicos'
    })
    logger.info("Modo: 1 caso típico")

elif opcao == '2':
    n_casos = int(input("Quantos casos: ").strip())
    variacao_pct = float(input("Variação % (ex: 10): ").strip())
    for i in range(n_casos):
        inputs_variados = {}
        for var_name, valor_tipico in config_dt['valores_tipicos'].items():
            variacao = np.random.uniform(-variacao_pct/100, variacao_pct/100)
            inputs_variados[var_name] = valor_tipico * (1 + variacao)
        casos_teste.append({
            'id': i + 1,
            'inputs': inputs_variados,
            'descricao': f'Variação ±{variacao_pct}%'
        })
    logger.info(f"Modo: {n_casos} casos ±{variacao_pct}%")

elif opcao == '3':
    casos_teste.append({'id': 1, 'inputs': {k: v * 1.5 for k, v in config_dt['valores_tipicos'].items()}, 'descricao': '+50%'})
    casos_teste.append({'id': 2, 'inputs': {k: v * 0.5 for k, v in config_dt['valores_tipicos'].items()}, 'descricao': '-50%'})
    logger.info("Modo: Teste de estresse")

elif opcao == '4':
    caminho_csv = os.path.join(PASTA_CONTROLE, 'casos_teste.csv')
    if not os.path.exists(caminho_csv):
        print(f"\n❌ Arquivo não encontrado\n")
        exit(1)
    
    df_casos = pd.read_csv(caminho_csv)
    print(f"\n✅ {len(df_casos)} casos carregados\n")
    
    for idx, row in df_casos.iterrows():
        caso_id = int(row['ID'])
        descricao = row.get('DESCRICAO', f'Caso {caso_id}')
        inputs = {col: float(row[col]) for col in df_casos.columns if col not in ['ID', 'DESCRICAO']}
        casos_teste.append({'id': caso_id, 'inputs': inputs, 'descricao': descricao})
    logger.info(f"Modo: {len(df_casos)} casos CSV")

print(f"✅ {len(casos_teste)} caso(s) preparado(s)\n")

# Validar casos
torres = identificar_torres(list(config_dt['valores_tipicos'].keys()))
if torres:
    for caso in casos_teste:
        caso['inputs'] = validar_e_corrigir_inputs(caso['inputs'], torres)
    print(f"✅ Casos validados ({len(torres)} torres)\n")

# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAR ARQUIVOS DE COMUNICAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

caminho_inputs = os.path.join(PASTA_CONTROLE, "inputs_compartilhados.json")
caminho_decisoes = os.path.join(PASTA_CONTROLE, "decisoes.json")
caminho_status = os.path.join(PASTA_CONTROLE, "status.json")
caminho_comando = os.path.join(PASTA_CONTROLE, "comando_parar.json")

escrever_json_seguro(caminho_inputs, {"novo_dado": False})
escrever_json_seguro(caminho_decisoes, {"parar": False})
escrever_json_seguro(caminho_status, {"aspen_finalizado": False})
escrever_json_seguro(caminho_comando, {"parar": False})

# ═══════════════════════════════════════════════════════════════════════════
# AGUARDAR MÓDULOS
# ═══════════════════════════════════════════════════════════════════════════

print("⏳ Aguardando Módulo Keras e Módulo Aspen...")
input("Pressione ENTER quando ambos estiverem rodando...\n")
logger.info("Iniciando execução de casos")

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTAR CASOS
# ═══════════════════════════════════════════════════════════════════════════

print("="*80)
print("EXECUTANDO CASOS".center(80))
print("="*80 + "\n")

resultados = []
timestamp_inicio = datetime.now().isoformat()

# Timeouts configuráveis
timeout_keras = CONFIG['control_system']['timeouts']['keras']
timeout_aspen = CONFIG['control_system']['timeouts']['aspen']

for caso in casos_teste:
    caso_id = caso['id']
    inputs = caso['inputs']
    descricao = caso['descricao']
    
    print(f"[{caso_id}/{len(casos_teste)}] {descricao}")
    inicio_caso = time.time()
    
    # Enviar inputs
    data_inputs = {
        "timestamp": datetime.now().isoformat(),
        "caso_id": caso_id,
        "novo_dado": True,
        "inputs": inputs
    }
    
    if not escrever_json_seguro(caminho_inputs, data_inputs):
        print(f"   ❌ Falha ao enviar inputs\n")
        logger.error(f"Caso {caso_id}: Falha ao enviar inputs")
        continue
    
    # Aguardar Keras
    inicio = time.time()
    decisao = None
    
    while time.time() - inicio < timeout_keras:
        decisao = ler_json_seguro(caminho_decisoes, tentativas=2, delay=0.05)
        if decisao and decisao.get('caso_id') == caso_id:
            break
        time.sleep(0.2)
    
    if not decisao or decisao.get('caso_id') != caso_id:
        print(f"   ⚠️  Keras timeout ({timeout_keras}s)\n")
        logger.warning(f"Caso {caso_id}: Keras timeout")
        continue
    
    keras_parar = decisao.get('parar', False)
    outputs_keras = decisao.get('outputs_preditos', {})
    
    # Exibir target
    target_keras = outputs_keras.get(TARGET_VARIABLE)
    if target_keras is not None:
        print(f"   🤖 Keras [{TARGET_VARIABLE}]: {target_keras:.4f}")
    
    if keras_parar:
        problemas = decisao.get('problemas', [])
        print(f"   🚨 Keras detectou {len(problemas)} problema(s) — Aspen continuará")
        logger.warning(f"Caso {caso_id}: Keras risco - {problemas}")
    
    # Sempre deixa Aspen rodar
    escrever_json_seguro(caminho_comando, {"parar": False, "caso_id": None})
    
    # Aguardar Aspen
    inicio = time.time()
    status = None
    
    while time.time() - inicio < timeout_aspen:
        status = ler_json_seguro(caminho_status, tentativas=2, delay=0.05)
        if status and status.get('caso_id') == caso_id:
            if status.get('aspen_finalizado'):
                break
        time.sleep(0.5)
    
    if not status:
        print(f"   ⚠️  Aspen timeout ({timeout_aspen}s)\n")
        logger.warning(f"Caso {caso_id}: Aspen timeout")
        continue
    
    outputs_aspen = status.get('outputs', {})
    aspen_abortado = status.get('abortado', False)
    tempo_total = time.time() - inicio_caso
    
    # Target Aspen
    target_aspen = outputs_aspen.get(TARGET_VARIABLE)
    if target_aspen is not None:
        print(f"   🏭 Aspen [{TARGET_VARIABLE}]: {target_aspen:.4f}")
        
        if target_keras is not None:
            erro_target = abs(target_keras - target_aspen)
            erro_target_pct = (erro_target / target_aspen * 100) if target_aspen != 0 else 0
            print(f"   📊 Erro target: {erro_target:.4f} ({erro_target_pct:.2f}%)")
    elif aspen_abortado:
        print(f"   🛑 Aspen: Simulação abortada")
    
    # Registrar no BD
    db.registrar_caso(
        caso_id, inputs, outputs_keras, outputs_aspen,
        keras_parar, aspen_abortado, tempo_total
    )
    
    # Comparar variáveis
    comparacoes = []
    todos_outputs = config_dt.get('nomes_outputs', [])
    if not todos_outputs:
        todos_outputs = set(outputs_keras.keys()) | set(outputs_aspen.keys())
    
    for var_name in todos_outputs:
        keras_val = outputs_keras.get(var_name)
        aspen_val = outputs_aspen.get(var_name)
        
        if keras_val is not None and aspen_val is not None:
            try:
                keras_val = float(keras_val)
                aspen_val = float(aspen_val)
                erro_abs = abs(keras_val - aspen_val)
                erro_pct = abs(erro_abs / aspen_val * 100) if aspen_val != 0 else 0
                
                comparacoes.append({
                    'variavel': var_name,
                    'keras': keras_val,
                    'aspen': aspen_val,
                    'erro_abs': erro_abs,
                    'erro_pct': erro_pct
                })
            except:
                pass
    
    print(f"   ✅ Concluído ({tempo_total:.1f}s, {len(comparacoes)} outputs)\n")
    logger.info(f"Caso {caso_id} concluído em {tempo_total:.1f}s")
    
    resultado = {
        'caso_id': caso_id,
        'descricao': descricao,
        'keras_detectou_risco': keras_parar,
        'aspen_abortado': aspen_abortado,
        'tempo_total': tempo_total,
        'comparacoes': comparacoes,
        'target_aspen': outputs_aspen.get(TARGET_VARIABLE),
        'target_keras': outputs_keras.get(TARGET_VARIABLE) if outputs_keras else None
    }
    resultados.append(resultado)
    
    # Métricas periódicas
    if caso_id % 10 == 0 and caso_id > 0:
        metricas = db.calcular_metricas_acuracia()
        if metricas:
            print(f"\n📊 MÉTRICAS (últimos {CONFIG['control_system']['metrics']['window_size']} casos):")
            print(f"   MAE:   {metricas['mae']:.4f}")
            print(f"   R²:    {metricas['r2']:.4f}")
            print(f"   MAPE:  {metricas['mape']:.2f}%")
            print(f"   SMAPE: {metricas['smape']:.2f}%")
            
            if metricas['drift_detectado']:
                print(f"   ⚠️  DRIFT DETECTADO!")
            
            print(f"   Variáveis: {metricas['n_variaveis']}\n")
            logger.info(f"Métricas: MAE={metricas['mae']:.4f}, R²={metricas['r2']:.4f}, SMAPE={metricas['smape']:.2f}%")
    
    # Buffer retreino
    buffer_count = db.contar_buffer_retreino()
    if buffer_count >= CONFIG['control_system']['metrics']['buffer_size']:
        print(f"\n🔄 Buffer de retreino cheio ({buffer_count} casos)")
        print(f"   💡 Retreinamento recomendado\n")
        logger.info(f"Buffer retreino: {buffer_count} casos")
    
    time.sleep(1)

# ═══════════════════════════════════════════════════════════════════════════
# RELATÓRIO FINAL
# ═══════════════════════════════════════════════════════════════════════════

print("="*80)
print("RELATÓRIO FINAL".center(80))
print("="*80 + "\n")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bias_str      = "com_bias"   if _cfg_raw.get('flags', {}).get('usar_bias')      else "sem_bias"
validacao_str = "validacao"  if MODO_VALIDACAO                                   else "producao"
nome_base     = f"relatorio_{validacao_str}_{bias_str}_{timestamp}"


# JSON
relatorio_json = os.path.join(PASTA_RESULTADOS, f"{nome_base}.json")
with open(relatorio_json, 'w', encoding='utf-8') as f:
    json.dump(resultados, f, indent=2, ensure_ascii=False)
print(f"📄 JSON: {os.path.basename(relatorio_json)}")

# CSV
linhas_csv = []
for res in resultados:
    linha_base = {
        'caso_id': res['caso_id'],
        'descricao': res['descricao'],
        'keras_risco': res['keras_detectou_risco'],
        'aspen_abortado': res['aspen_abortado'],
        'tempo_total': res['tempo_total']
    }

    if res['comparacoes']:
        for comp in res['comparacoes']:
            linha = linha_base.copy()
            linha.update({
                'variavel': comp['variavel'],
                'keras': comp['keras'],
                'aspen': comp['aspen'],
                'erro_abs': comp['erro_abs'],
                'erro_pct': comp['erro_pct']
            })
            linhas_csv.append(linha)
    else:
        # Caso abortado: salva 1 linha só com o valor do Keras, aspen fica vazio
        linha = linha_base.copy()
        linha.update({
            'variavel': TARGET_VARIABLE,
            'keras': res.get('target_keras'),
            'aspen': None,
            'erro_abs': None,
            'erro_pct': None
        })
        linhas_csv.append(linha)

if linhas_csv:
    df = pd.DataFrame(linhas_csv)
    relatorio_csv = os.path.join(PASTA_RESULTADOS, f"{nome_base}.csv")
    df.to_csv(relatorio_csv, index=False)
    print(f"📊 CSV: {os.path.basename(relatorio_csv)}\n")
    
    # Estatísticas
    print("ESTATÍSTICAS:\n")
    print(f"   Total casos: {len(resultados)}")
    print(f"   Riscos (Keras): {sum(1 for r in resultados if r['keras_detectou_risco'])}")
    print(f"   Abortados (Aspen): {sum(1 for r in resultados if r['aspen_abortado'])}")
    print(f"   Erro médio (MAE): {df['erro_abs'].mean():.4f}")
    print(f"   Erro % médio (MAPE): {df['erro_pct'].mean():.2f}%")
    
    smape_global = calcular_smape(df['aspen'].values, df['keras'].values)
    print(f"   SMAPE global: {smape_global:.2f}%")
    print(f"   R² global: {r2_score(df['aspen'], df['keras']):.4f}")
    print(f"   Tempo médio/caso: {df.groupby('caso_id')['tempo_total'].first().mean():.1f}s")
    
    if MODO_VALIDACAO:
        falsos_alarmes = sum(
            1 for r in resultados
            if r['keras_detectou_risco']
            and r.get('target_aspen') is not None
            and r['target_aspen'] >= LIMITE_TARGET
        )
        alarmes_corretos = sum(
            1 for r in resultados
            if r['keras_detectou_risco']
            and r.get('target_aspen') is not None
            and r['target_aspen'] < LIMITE_TARGET
        )
        print(f"\n🎯 ANÁLISE DE ALARMES [MODO VALIDAÇÃO]:")
        print(f"   Alarmes corretos: {alarmes_corretos}")
        print(f"   Falsos alarmes:   {falsos_alarmes}")
        total = falsos_alarmes + alarmes_corretos
        if total > 0:
            print(f"   Taxa falsos:      {falsos_alarmes/total*100:.1f}%")
    
    # Target específico
    df_target = df[df['variavel'] == TARGET_VARIABLE]
    if len(df_target) > 0:
        print(f"\n🎯 ESTATÍSTICAS [{TARGET_VARIABLE}]:")
        print(f"   MAE: {df_target['erro_abs'].mean():.4f}")
        print(f"   MAPE: {df_target['erro_pct'].mean():.2f}%")
        smape_target = calcular_smape(df_target['aspen'].values, df_target['keras'].values)
        print(f"   SMAPE: {smape_target:.2f}%")
        print(f"   R²: {r2_score(df_target['aspen'], df_target['keras']):.4f}")
    
    # Finalizar no BD
    mae_final = df['erro_abs'].mean()
    r2_final = r2_score(df['aspen'], df['keras'])
    taxa_alertas = (sum(1 for r in resultados if r['keras_detectou_risco']) / len(resultados)) * 100
    
    db.finalizar_experimento(
        timestamp_inicio, len(resultados), len(resultados), 0,
        taxa_alertas, mae_final, r2_final, smape_global
    )
    
    logger.info(f"Experimento finalizado: {len(resultados)} casos, MAE={mae_final:.4f}, R²={r2_final:.4f}")

print("\n" + "="*80)
print("✅ CONCLUÍDO".center(80))
print("="*80 + "\n")

logger.info("Sistema de Controle V3 finalizado")