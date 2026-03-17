"""
════════════════════════════════════════════════════════════════════════════════
    MÓDULO KERAS V3.3 (LITE) - Runtime de Inferência e Segurança
    
    VERSÃO 3.3 FINAL - Compatível com config_final.json E config_digital_twin.json
    
    FOCO: Performance e Estabilidade
    ✅ Arquitetura Híbrida: Modelo Base ResNet + Especialistas
    ✅ Verificação de Segurança: Detecção de riscos operacionais
    ✅ Histórico: Log de predições em SQLite
    ✅ Alta Velocidade: Sem sobrecarga de cálculos de drift ou retreino
    ✅ Configuração Centralizada: Usa config.yaml
    ✅ Compatibilidade Automática: Detecta tipo de config automaticamente
════════════════════════════════════════════════════════════════════════════════
"""

import json
import time
import numpy as np
import sqlite3
import logging
import sys
import os
from datetime import datetime
from pathlib import Path
import warnings
import yaml

# Ignorar avisos do TF/Keras
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════
# 🔧 CARREGAMENTO DE CONFIGURAÇÕES (YAML)
# ═══════════════════════════════════════════════════════════════════════════

# 1. Identificar a Raiz do Projeto Automaticamente
BASE_DIR = Path(__file__).resolve().parent.parent

print(f"📂 Raiz do Projeto detectada: {BASE_DIR}")

# 2. Carregar o arquivo YAML
config_path = BASE_DIR / "config" / "config.yaml"

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    print("✅ Configurações YAML carregadas!\n")
except FileNotFoundError:
    print(f"❌ ERRO: Arquivo de config não encontrado em: {config_path}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# 🎛️ MODO DE INFERÊNCIA
# ═══════════════════════════════════════════════════════════════════════════

USAR_ESPECIALISTAS = cfg['flags'].get('usar_especialistas', True)
USAR_BIAS = cfg['flags'].get('usar_bias', True)
# 3. Configurar Caminhos
PASTA_MODELOS = BASE_DIR / cfg['paths']['output_modelos']
PASTA_CONTROLE = BASE_DIR / "controle"
PASTA_HISTORICO = BASE_DIR / "historico"

# Criar pastas necessárias
PASTA_CONTROLE.mkdir(exist_ok=True)
PASTA_HISTORICO.mkdir(exist_ok=True)

# Arquivos importantes
CONFIG_DIGITAL_TWIN_PATH = PASTA_MODELOS / "config_digital_twin.json"
CONFIG_FINAL_PATH = PASTA_MODELOS / "config_final.json"
DB_PATH = PASTA_HISTORICO / "digital_twin.db"

# Adicionar pasta dos modelos ao path
sys.path.append(str(PASTA_MODELOS))

print(f"📁 Pastas configuradas:")
print(f"   • Modelos: {PASTA_MODELOS}")
print(f"   • Controle: {PASTA_CONTROLE}")
print(f"   • Histórico: {PASTA_HISTORICO}\n")

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING (com suporte a Unicode no Windows)
# ═══════════════════════════════════════════════════════════════════════════

# Configurar encoding UTF-8 para o log file
file_handler = logging.FileHandler(
    PASTA_HISTORICO / 'modulo_keras_lite.log',
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

# Stream handler para console (sem emojis no Windows)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

# Detectar se está no Windows para remover emojis dos logs
IS_WINDOWS = sys.platform.startswith('win')

def log_info(message):
    """Log com remoção automática de emojis no Windows"""
    if IS_WINDOWS:
        # Remover emojis comuns
        message = message.replace('✅', '[OK]')
        message = message.replace('❌', '[ERRO]')
        message = message.replace('⚠️', '[AVISO]')
        message = message.replace('🔄', '[PROC]')
        message = message.replace('📊', '[INFO]')
        message = message.replace('🛑', '[STOP]')
        message = message.replace('🧠', '[ESP]')
        message = message.replace('🤖', '[BASE]')
        message = message.replace('🔴', '[CRIT]')
        message = message.replace('🟡', '[WARN]')
    logger.info(message)

# Validação Crítica - verificar qual config existe
if CONFIG_DIGITAL_TWIN_PATH.exists():
    CONFIG_PATH = CONFIG_DIGITAL_TWIN_PATH
    CONFIG_TYPE = "digital_twin"
    log_info(f"✅ Usando config_digital_twin.json")
elif CONFIG_FINAL_PATH.exists():
    CONFIG_PATH = CONFIG_FINAL_PATH
    CONFIG_TYPE = "final"
    log_info(f"✅ Usando config_final.json")
else:
    logger.error(f"❌ ERRO CRÍTICO: Nenhum arquivo de configuração encontrado em: {PASTA_MODELOS}")
    log_info("💡 Execute primeiro:")
    log_info("   1. criar_modelo.py (treinar modelo)")
    log_info("   2. extrator_sincronizado.py (gerar config)")
    sys.exit(1)

try:
    from digital_twin_predictor import DigitalTwinPredictor
    log_info("✅ DigitalTwinPredictor importado com sucesso")
except ImportError as e:
    logger.error(f"❌ ERRO CRÍTICO: 'digital_twin_predictor.py' não encontrado em: {PASTA_MODELOS}")
    logger.error(f"   Detalhes: {e}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# BANCO DE DADOS (Apenas Histórico de Predição)
# ═══════════════════════════════════════════════════════════════════════════

class DatabaseLite:
    """Banco de dados simplificado para histórico de inferência"""
    
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._criar_tabelas()
        log_info(f"✅ DB Lite conectado: {self.db_path.name}")
    
    def _criar_tabelas(self):
        # Tabela de predições
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS predicoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                caso_id INTEGER,
                inputs TEXT,
                outputs_preditos TEXT,
                parar INTEGER,
                n_problemas INTEGER,
                usou_especialista INTEGER,
                modelo_versao TEXT,
                tempo_ms REAL
            )
        ''')
        
        # Tabela de alertas
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                caso_id INTEGER,
                variavel TEXT,
                tipo_limite TEXT,
                valor_predito REAL,
                limite REAL,
                severidade TEXT
            )
        ''')
        
        # Tabela de estatísticas
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS estatisticas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                total_predicoes INTEGER,
                total_alertas INTEGER,
                taxa_alerta REAL,
                tempo_medio_ms REAL
            )
        ''')
        
        self.conn.commit()
        log_info("✅ Tabelas do banco criadas/verificadas")
    
    def registrar_predicao(self, caso_id, inputs, outputs, parar, n_problemas, usou_especialista, versao, tempo_ms):
        """Registra uma predição no histórico"""
        try:
            self.cursor.execute('''
                INSERT INTO predicoes 
                (timestamp, caso_id, inputs, outputs_preditos, parar, n_problemas, usou_especialista, modelo_versao, tempo_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                caso_id,
                json.dumps(inputs),
                json.dumps(outputs),
                1 if parar else 0,
                n_problemas,
                1 if usou_especialista else 0,
                versao,
                tempo_ms
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao registrar predição: {e}")
    
    def registrar_alerta(self, caso_id, problema):
        """Registra um alerta de limite violado"""
        try:
            self.cursor.execute('''
                INSERT INTO alertas 
                (timestamp, caso_id, variavel, tipo_limite, valor_predito, limite, severidade)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                caso_id,
                problema['variavel'],
                problema['tipo'],
                problema['valor_predito'],
                problema['limite'],
                'CRITICO' if problema.get('critica', False) else 'AVISO'
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao registrar alerta: {e}")
    
    def atualizar_estatisticas(self, total_predicoes, total_alertas, tempo_medio_ms):
        """Atualiza estatísticas gerais"""
        try:
            taxa_alerta = (total_alertas / total_predicoes * 100) if total_predicoes > 0 else 0.0
            
            self.cursor.execute('''
                INSERT INTO estatisticas 
                (timestamp, total_predicoes, total_alertas, taxa_alerta, tempo_medio_ms)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                total_predicoes,
                total_alertas,
                taxa_alerta,
                tempo_medio_ms
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao atualizar estatísticas: {e}")
    
    def obter_estatisticas(self):
        """Retorna estatísticas gerais"""
        try:
            # Total de predições
            self.cursor.execute("SELECT COUNT(*) FROM predicoes")
            total_predicoes = self.cursor.fetchone()[0]
            
            # Total de alertas
            self.cursor.execute("SELECT COUNT(*) FROM predicoes WHERE parar = 1")
            total_alertas = self.cursor.fetchone()[0]
            
            # Tempo médio
            self.cursor.execute("SELECT AVG(tempo_ms) FROM predicoes")
            tempo_medio = self.cursor.fetchone()[0] or 0.0
            
            # Taxa de uso de especialistas
            self.cursor.execute("SELECT COUNT(*) FROM predicoes WHERE usou_especialista = 1")
            total_especialistas = self.cursor.fetchone()[0]
            
            return {
                'total_predicoes': total_predicoes,
                'total_alertas': total_alertas,
                'taxa_alerta': (total_alertas / total_predicoes * 100) if total_predicoes > 0 else 0.0,
                'tempo_medio_ms': tempo_medio,
                'total_especialistas': total_especialistas,
                'taxa_especialistas': (total_especialistas / total_predicoes * 100) if total_predicoes > 0 else 0.0
            }
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return None
    
    def fechar(self):
        """Fecha conexão com o banco"""
        self.conn.close()
        logger.info("📊 Banco de dados fechado")

# ═══════════════════════════════════════════════════════════════════════════
# LEITURA/ESCRITA JSON SEGURA
# ═══════════════════════════════════════════════════════════════════════════

def ler_json_seguro(caminho: Path, tentativas: int = 5, delay: float = 0.05):
    """Lê JSON com retry e validação"""
    for i in range(tentativas):
        try:
            if not caminho.exists() or caminho.stat().st_size == 0:
                time.sleep(delay)
                continue
            
            with open(caminho, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except json.JSONDecodeError:
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Erro ao ler {caminho.name}: {e}")
            time.sleep(delay)
    
    return None

def escrever_json_seguro(caminho: Path, dados: dict):
    """Escreve JSON com segurança (atomic write) e conversão de tipos NumPy"""
    try:
        # Converter tipos NumPy para tipos Python nativos
        def converter_numpy(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, dict):
                return {k: converter_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [converter_numpy(item) for item in obj]
            return obj
        
        dados_convertidos = converter_numpy(dados)
        
        caminho_temp = caminho.with_suffix('.tmp')
        
        with open(caminho_temp, 'w', encoding='utf-8') as f:
            json.dump(dados_convertidos, f, indent=2, ensure_ascii=False)
        
        # Atomic replace
        if caminho.exists():
            caminho.unlink()
        caminho_temp.rename(caminho)
        
        return True
    except Exception as e:
        logger.error(f"Erro ao escrever {caminho.name}: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# PREDITOR DE INFERÊNCIA (WRAPPER COM COMPATIBILIDADE AUTOMÁTICA)
# ═══════════════════════════════════════════════════════════════════════════

class PreditorInferencia:
    """Wrapper focado apenas em inferência e segurança - compatível com ambos os formatos de config"""
    
    def __init__(self, pasta_modelos, db_path, config_type):
        log_info(f"🔄 Inicializando preditor...")
        log_info(f"   Modo especialistas: {'ATIVADO' if USAR_ESPECIALISTAS else 'DESATIVADO'}")
        self.config_type = config_type

        log_info(f"   Pasta modelos: {pasta_modelos}")
        log_info(f"   Tipo de config: {config_type}")
        
        self.config_type = config_type
        
        # 1. Carregar Sistema Híbrido (usando sua classe existente)
        try:
            self.core = DigitalTwinPredictor(pasta_modelos)
            if not USAR_ESPECIALISTAS:
                self.core.especialistas = {}
                log_info("⚠️  Especialistas DESATIVADOS - usando apenas modelo base")
            else:
                log_info(f"✅ Especialistas ATIVOS: {len(self.core.especialistas)}")
        except Exception as e:
            logger.error(f"❌ FALHA FATAL ao carregar modelos: {e}")
            raise e
        
        # 2. Carregar e normalizar configuração
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)
        
        # Normalizar config para formato unificado
        self.config_modelo = self._normalizar_config(raw_config)
        
        log_info(f"   • Versão: {self.config_modelo['versao']}")
        log_info(f"   • Inputs: {len(self.config_modelo['inputs'])}")
        log_info(f"   • Outputs: {len(self.config_modelo['outputs'])}")
        log_info(f"   • Especialistas: {len(self.core.especialistas)}")
        
        # 3. Conectar BD
        self.db = DatabaseLite(db_path)
        
        # 4. Carregar Limites Críticos
        self.limites_criticos = self.config_modelo.get('limites_criticos', {})
        self.variaveis_criticas = self.config_modelo.get('variaveis_criticas_lista', [])
        
        log_info(f"   • Monitorando {len(self.limites_criticos)} variáveis críticas")
        
        # Listar variáveis críticas
        for var_nome in list(self.limites_criticos.keys())[:3]:
            limite_info = self.limites_criticos[var_nome]
            log_info(f"      - {var_nome}: {limite_info['tipo']} = {limite_info['valor']}")
        
        if len(self.limites_criticos) > 3:
            log_info(f"      ... e mais {len(self.limites_criticos) - 3}")
        
        log_info("✅ Preditor inicializado com sucesso!\n")
    
    def _normalizar_config(self, raw_config):
        """
        Normaliza configuração para formato unificado independente da origem
        
        Retorna dict com estrutura padronizada:
        {
            'versao': str,
            'inputs': list,
            'outputs': list,
            'limites_criticos': dict,
            'variaveis_criticas_lista': list,
            'valores_tipicos': dict
        }
        """
        config_normalizado = {}
        
        if self.config_type == "digital_twin":
            # Estrutura config_digital_twin.json
            config_normalizado['versao'] = raw_config.get('projeto', {}).get('versao', '1.0')
            config_normalizado['inputs'] = raw_config.get('variaveis', {}).get('inputs', [])
            config_normalizado['outputs'] = raw_config.get('variaveis', {}).get('outputs', [])
            
            # Limites críticos
            variaveis_criticas = raw_config.get('variaveis_criticas', {})
            config_normalizado['limites_criticos'] = variaveis_criticas.get('limites', {})
            config_normalizado['variaveis_criticas_lista'] = variaveis_criticas.get('lista', [])
            
            # Valores típicos
            config_normalizado['valores_tipicos'] = raw_config.get('estatisticas_inputs', {}).get('valores_tipicos', {})
            
        else:  # config_type == "final"
            # Estrutura config_final.json
            config_normalizado['versao'] = raw_config.get('versao', '1.0')
            config_normalizado['inputs'] = raw_config.get('inputs', [])
            
            # Para outputs, usar a lista de nomes se existir, senão gerar genéricos
            if 'outputs' in raw_config:
                config_normalizado['outputs'] = raw_config['outputs']
            else:
                n_outputs = raw_config.get('modelo', {}).get('n_outputs', 0)
                config_normalizado['outputs'] = [f'OUT_{i}' for i in range(n_outputs)]
            
            # Limites críticos - pode não existir no config_final.json
            config_normalizado['limites_criticos'] = raw_config.get('limites_criticos', {})
            config_normalizado['variaveis_criticas_lista'] = raw_config.get('variaveis_criticas', [])
            
            # Valores típicos
            config_normalizado['valores_tipicos'] = raw_config.get('valores_tipicos', {})
        
        return config_normalizado
    
    def preparar_inputs(self, inputs_dict):
        """Converte dict para array na ordem do treinamento"""
        lista_inputs = []
        
        for nome in self.config_modelo['inputs']:
            if nome in inputs_dict:
                lista_inputs.append(float(inputs_dict[nome]))
            else:
                # Usar valor típico se disponível, senão 0.0
                valor_tipico = self.config_modelo['valores_tipicos'].get(nome, 0.0)
                lista_inputs.append(valor_tipico)
                logger.warning(f"⚠️ Input '{nome}' não fornecido, usando valor típico: {valor_tipico}")
        
        return np.array([lista_inputs])

    def fazer_predicao(self, inputs_array):
        """Executa inferência rápida"""
        # Usar predict_with_info para ter informações detalhadas
        resultado = self.core.predict_with_info(inputs_array)
        
        valores = resultado['predicoes'][0]
        
        # Formatar outputs
        outputs_formatados = {}
        for i, nome in enumerate(self.config_modelo['outputs']):
            if i < len(valores):
                outputs_formatados[nome] = float(valores[i])
        
        # Verificar se usou especialista
        usou_especialista = np.any(resultado['usou_especialista'])
        
        return outputs_formatados, usou_especialista, []

    def verificar_limites(self, outputs_dict):
        """Verifica segurança operacional"""
        problemas = []
        
        for var_name, regra in self.limites_criticos.items():
            if var_name not in outputs_dict:
                continue
            
            val = outputs_dict[var_name]
            tipo = regra['tipo']
            limite = regra['valor']
            
            violou = False
            if tipo == 'max' and val > limite:
                violou = True
            elif tipo == 'min' and val < limite:
                violou = True
            
            if violou:
                problemas.append({
                    'variavel': var_name,
                    'tipo': tipo,
                    'valor_predito': val,
                    'limite': limite,
                    'descricao': regra.get('descricao', ''),
                    'critica': var_name in self.variaveis_criticas
                })
        
        return len(problemas) > 0, problemas

# ═══════════════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("MÓDULO KERAS V3.3 (LITE) - INFERÊNCIA PURA".center(80))
print("="*80 + "\n")

try:
    preditor = PreditorInferencia(PASTA_MODELOS, DB_PATH, CONFIG_TYPE)
    print(f"✅ Sistema pronto para inferência!")
    print(f"   • Tipo de config: {CONFIG_TYPE}")
    print(f"   • Projeto: Digital Twin")
    print(f"   • Arquitetura: XXX + Especialistas")
    print(f"   • Modo:        {'Base + Especialistas' if USAR_ESPECIALISTAS else 'Somente Base'}")
    print(f"   • Especialistas ativos: {len(preditor.core.especialistas)}")
    print(f"   • Inputs: {len(preditor.config_modelo['inputs'])}")
    print(f"   • Outputs: {len(preditor.config_modelo['outputs'])}\n")
    print(f"   • Inputs: {len(preditor.config_modelo['inputs'])}")
    print(f"   • Outputs: {len(preditor.config_modelo['outputs'])}\n")
except Exception as e:
    logger.error(f"❌ Falha na inicialização: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("🔄 Aguardando dados em inputs_compartilhados.json...\n")

# Contadores
contador_predicoes = 0
contador_alertas = 0
ultimo_caso = None
tempos_predicao = []

# Correção de bias online
bias_historico = {}      # {variavel: [erros]}
bias_atual = {}          # {variavel: valor_medio}
N_BIAS = 20              # janela de casos para calcular bias
ultimo_caso_aspen_id  = None
ultimo_outputs_keras  = {}
caminho_status = PASTA_CONTROLE / "status.json"

# Caminhos de arquivos de controle
caminho_inputs = PASTA_CONTROLE / "inputs_compartilhados.json"
caminho_decisoes = PASTA_CONTROLE / "decisoes.json"
caminho_comando_parar = PASTA_CONTROLE / "comando_parar.json"

# Loop principal
while True:
    try:
        # 1. Ler Inputs
        data = ler_json_seguro(caminho_inputs)
        
        # Esperar novo dado
        if not data or not data.get("novo_dado", False):
            time.sleep(0.02)  # Loop mais rápido (50 Hz)
            continue
        
        caso_id = data.get("caso_id")
        if caso_id == ultimo_caso:
            time.sleep(0.02)
            continue
        
        ultimo_caso = caso_id
        start_time = time.time()
        
        # 2. Executar Pipeline de Inferência
        inputs_dict = data.get("inputs", {})
        inputs_array = preditor.preparar_inputs(inputs_dict)
        
        # Predição
        outputs_preditos, usou_especialista, alertas_predictor = preditor.fazer_predicao(inputs_array)

        # Aplicar bias se disponível
        if USAR_BIAS and bias_atual:
            for var in outputs_preditos:
                if var in bias_atual:
                    outputs_preditos[var] = outputs_preditos[var] + bias_atual[var]
        
        # Segurança (verificar limites)
        parar, problemas = preditor.verificar_limites(outputs_preditos)
        
        # Combinar alertas do predictor com problemas de limites
        todos_problemas = problemas.copy()
        
        # Calcular tempo
        tempo_ms = (time.time() - start_time) * 1000
        tempos_predicao.append(tempo_ms)
        contador_predicoes += 1
        
        # 3. Registrar Histórico
        preditor.db.registrar_predicao(
            caso_id,
            inputs_dict,
            outputs_preditos,
            parar,
            len(todos_problemas),
            usou_especialista,
            preditor.config_modelo['versao'],
            tempo_ms
        )
        
        # Registrar alertas individuais
        if parar:
            contador_alertas += 1
            for problema in problemas:
                preditor.db.registrar_alerta(caso_id, problema)
        
        # 4. Enviar Resposta ao Controlador
        decisao = {
            "timestamp": datetime.now().isoformat(),
            "caso_id": caso_id,
            "parar": parar,
            "n_problemas": len(todos_problemas),
            "problemas": todos_problemas,
            "outputs_preditos": outputs_preditos,
            "usou_especialista": usou_especialista,
            "tempo_ms": tempo_ms
        }
        escrever_json_seguro(caminho_decisoes, decisao)

        status_aspen = ler_json_seguro(caminho_status)
        if USAR_BIAS and status_aspen and status_aspen.get('caso_id') == ultimo_caso_aspen_id:
            outputs_aspen = status_aspen.get('outputs', {})
            if outputs_aspen:
                for var, keras_val in ultimo_outputs_keras.items():
                    aspen_val = outputs_aspen.get(var)
                    if aspen_val is not None:
                        try:
                            erro = float(aspen_val) - float(keras_val)
                            if var not in bias_historico:
                                bias_historico[var] = []
                            bias_historico[var].append(erro)
                            if len(bias_historico[var]) > N_BIAS:
                                bias_historico[var].pop(0)
                            bias_atual[var] = float(np.mean(bias_historico[var]))
                        except:
                            pass
            target = 'PRODUTO_ACETA-01_MOLEFRAC_MIXED'
            n = len(bias_historico.get(target, []))
            if n >= N_BIAS:
                print(f"\n   📈 Bias ativo: {bias_atual[target]:+.4f} ({n} amostras)")
            elif n > 0:
                print(f"\n   📊 Coletando bias: {n}/{N_BIAS}...")
        ultimo_caso_aspen_id = caso_id
        ultimo_outputs_keras = outputs_preditos.copy()
        
        # 5. Interface e Logging
        status = "🛑" if parar else "✅"
        expert = "🧠" if usou_especialista else "🤖"
        
        # Calcular tempo médio
        tempo_medio = np.mean(tempos_predicao[-100:]) if tempos_predicao else 0.0
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Caso {caso_id:4d}: {status} ({tempo_ms:5.1f}ms | avg:{tempo_medio:5.1f}ms) [{expert}] [{contador_predicoes:5d} pred.]", end='\r')
        
        # Se houver problemas, mostrar
        if parar:
            print()  # Nova linha
            print(f"   {'─'*76}")
            print(f"   ⚠️  ALERTA DE RISCO OPERACIONAL - Caso {caso_id}")
            print(f"   {'─'*76}")
            
            for problema in problemas:
                tipo_emoji = "🔴" if problema.get('critica', False) else "🟡"
                print(f"   {tipo_emoji} {problema['variavel']}")
                print(f"      Valor predito: {problema['valor_predito']:.4f}")
                print(f"      Limite ({problema['tipo']}): {problema['limite']:.4f}")
                if problema.get('descricao'):
                    print(f"      Descrição: {problema['descricao']}")
            
            print(f"   {'─'*76}\n")
            
            # Comando de parada
            escrever_json_seguro(caminho_comando_parar, {
                "parar": True,
                "caso_id": caso_id,
                "timestamp": datetime.now().isoformat(),
                "motivo": "Limite crítico violado",
                "problemas": problemas
            })
            
            logger.warning(f"🛑 Risco detectado no Caso {caso_id}: {len(problemas)} problema(s)")
        
        # Atualizar estatísticas a cada 100 predições
        if contador_predicoes % 100 == 0:
            preditor.db.atualizar_estatisticas(
                contador_predicoes,
                contador_alertas,
                tempo_medio
            )

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido pelo usuário\n")
        break
    
    except Exception as e:
        logger.error(f"❌ Erro no loop: {e}", exc_info=True)
        time.sleep(0.5)

# ═══════════════════════════════════════════════════════════════════════════
# FINALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("📊 ESTATÍSTICAS FINAIS")
print("="*80 + "\n")

# Obter estatísticas do banco
stats = preditor.db.obter_estatisticas()

if stats:
    print(f"Total de predições:      {stats['total_predicoes']:,}")
    print(f"Total de alertas:        {stats['total_alertas']:,}")
    print(f"Taxa de alertas:         {stats['taxa_alerta']:.2f}%")
    print(f"Tempo médio:             {stats['tempo_medio_ms']:.2f} ms")
    print(f"Uso de especialistas:    {stats['total_especialistas']:,} ({stats['taxa_especialistas']:.1f}%)")
    
    if tempos_predicao:
        print(f"\nEstatísticas de tempo:")
        print(f"   • Mínimo:   {min(tempos_predicao):.2f} ms")
        print(f"   • Máximo:   {max(tempos_predicao):.2f} ms")
        print(f"   • Mediana:  {np.median(tempos_predicao):.2f} ms")

print(f"\n📁 Dados salvos em:")
print(f"   • Banco: {DB_PATH.name}")
print(f"   • Log: modulo_keras_lite.log")

# Fechar banco
preditor.db.fechar()
logger.info("✅ Módulo Keras Lite finalizado")

print("\n👋 Sistema encerrado com sucesso.\n")