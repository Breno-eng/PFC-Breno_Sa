"""
════════════════════════════════════════════════════════════════════════════════
    MÓDULO ASPEN V3.0 - Reescrito com lógica correta de simulação
    
    ORDEM CORRETA (baseada no script que funciona):
        1. setar inputs no Aspen
        2. Engine.Reinit()
        3. Engine.Run2()
        4. ler outputs
    
    COMUNICAÇÃO:
        LÊ:    controle/inputs_compartilhados.json
        ESCREVE: controle/status.json
════════════════════════════════════════════════════════════════════════════════
"""

import json
import sys
import io
import time
import pickle
import logging
import numpy as np
import win32com.client as win32
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
import yaml

# Força saída UTF-8 no Windows
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent.parent
config_path = BASE_DIR / "config" / "config.yaml"

with open(config_path, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

PASTA_MODELOS   = BASE_DIR / cfg['paths']['output_modelos']
PASTA_CONTROLE  = BASE_DIR / "controle"
PASTA_HISTORICO = BASE_DIR / "historico"
SCANNER_PATH    = BASE_DIR / "scan_total"

PASTA_CONTROLE.mkdir(exist_ok=True, parents=True)
PASTA_HISTORICO.mkdir(exist_ok=True, parents=True)

# Arquivos de comunicação
ARQUIVO_INPUTS  = PASTA_CONTROLE / "inputs_compartilhados.json"
ARQUIVO_STATUS  = PASTA_CONTROLE / "status.json"
ARQUIVO_COMANDO = PASTA_CONTROLE / "comando_parar.json"

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(PASTA_HISTORICO / 'modulo_aspen_v3.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# FUNÇÕES JSON
# ═══════════════════════════════════════════════════════════════════════════

def ler_json(caminho: Path, tentativas: int = 3) -> Optional[Dict]:
    for _ in range(tentativas):
        try:
            if not caminho.exists() or caminho.stat().st_size == 0:
                time.sleep(0.1)
                continue
            with open(caminho, 'r', encoding='utf-8') as f:
                return json.loads(f.read().strip())
        except:
            time.sleep(0.1)
    return None

def escrever_json(caminho: Path, dados: Dict) -> bool:
    try:
        tmp = caminho.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        if caminho.exists():
            caminho.unlink()
        tmp.rename(caminho)
        return True
    except Exception as e:
        logger.error(f"Erro ao escrever {caminho.name}: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# LEITURA DE OUTPUT COM FALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def ler_output(aspen, path: str, info: Dict, componentes_lista: list) -> Optional[float]:
    """
    Lê um output do Aspen com 3 fallbacks:
      1. node.Elements(componente).Value
      2. node.Value[componente]
      3. node.Value[idx_componente]
    Para outputs sem componente: node.Value direto
    """
    try:
        node = aspen.Tree.FindNode(path)
        if not node:
            return None

        if 'componente' in info:
            componente = info['componente']
            # Fallback 1
            try:
                return float(node.Elements(componente).Value)
            except:
                pass
            # Fallback 2
            try:
                return float(node.Value[componente])
            except:
                pass
            # Fallback 3
            try:
                if componente in componentes_lista:
                    idx = componentes_lista.index(componente)
                    return float(node.Value[idx])
            except:
                pass
            return None
        else:
            val = node.Value
            if hasattr(val, '__len__') and not isinstance(val, str):
                return float(val[0]) if len(val) > 0 else None
            return float(val)
    except:
        return None

# ═══════════════════════════════════════════════════════════════════════════
# SIMULAÇÃO (lógica do script que funciona)
# ═══════════════════════════════════════════════════════════════════════════

def simular(aspen, inputs_dict: Dict, inputs_paths: Dict) -> bool:
    """
    Ordem IDÊNTICA ao script que funciona:
      1. Setar TODOS os inputs (sem nenhum Reinit intermediário)
      2. Engine.Reinit()
      3. Engine.Run2()
    """
    # Setar NSTAGE primeiro, depois FEED_STAGE, depois resto — sem Reinit no meio
    nstage_vars = {v: val for v, val in inputs_dict.items() if "NSTAGE" in v}
    feed_vars   = {v: val for v, val in inputs_dict.items() if "FEED_STAGE" in v}
    outras_vars = {v: val for v, val in inputs_dict.items()
                   if "NSTAGE" not in v and "FEED_STAGE" not in v}
    
    total = len(inputs_dict)
    print(f"   ⚙️  Setando {total} variáveis...", end='', flush=True)

    for var, val in {**nstage_vars, **feed_vars, **outras_vars}.items():
        if var not in inputs_paths:
            continue
        try:
            node = aspen.Tree.FindNode(inputs_paths[var])
            if node:
                if any(x in var for x in ["NSTAGE", "FEED_STAGE"]):
                    print(f" {var}={int(round(float(val)))}", end='', flush=True)
                    node.Value = int(round(float(val)))
                else:
                    node.Value = float(val)
        except Exception as e:
            if "FEED_STAGE" in var:
                logger.debug(f"FEED_STAGE ignorado (normal): {var}")
            else:
                logger.warning(f"Erro ao setar {var}: {e}")

    # Reinit → Run2
    try:
        aspen.Engine.Reinit()
        time.sleep(0.5)
        aspen.Engine.Run2()
        time.sleep(0.5)
        return True
    except Exception as e:
        logger.error(f"Erro na simulação: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("  MÓDULO ASPEN V3.0")
print("="*70 + "\n")

# Carregar scanner
scanner_files = list(SCANNER_PATH.glob("*.pkl"))
if not scanner_files:
    logger.error(f"Nenhum PKL encontrado em: {SCANNER_PATH}")
    exit(1)

scanner_file = max(scanner_files, key=lambda p: p.stat().st_mtime)
logger.info(f"Scanner: {scanner_file.name}")

with open(scanner_file, 'rb') as f:
    dados_scanner = pickle.load(f)

CAMINHO_ASPEN      = Path(dados_scanner['arquivo'])
componentes_lista  = dados_scanner.get('componentes', [])
inputs_paths_total = dados_scanner['caminhos_com_valores']['INPUTS']
outputs_info       = dados_scanner['caminhos_com_valores']['OUTPUTS']

# Mapear paths de inputs
inputs_paths = {v: dados_scanner['caminhos_com_valores']['INPUTS'][v]['caminho']
                for v in inputs_paths_total}

# Mapear paths de outputs
outputs_paths = {v: info['caminho'] for v, info in outputs_info.items()}

logger.info(f"Inputs disponíveis: {len(inputs_paths)}")
logger.info(f"Outputs disponíveis: {len(outputs_paths)}")

# Conectar Aspen (único InitFromArchive2 — mantém estado correto entre casos)
print("⏳ Conectando ao Aspen Plus...")
try:
    aspen = win32.Dispatch('Apwn.Document')
    aspen.InitFromArchive2(str(CAMINHO_ASPEN))
    aspen.Visible = 0
    logger.info(f"✅ Aspen conectado: {CAMINHO_ASPEN.name}")
except Exception as e:
    logger.error(f"Erro ao conectar Aspen: {e}")
    exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("  🔄 AGUARDANDO INPUTS DO CONTROLADOR")
print("="*70 + "\n")

contador = 0
falhas   = 0

while True:
    try:
        # Ler inputs
        data = ler_json(ARQUIVO_INPUTS)

        if not data or not data.get("novo_dado"):
            time.sleep(0.1)
            continue

        caso_id     = data.get("caso_id", 0)
        inputs_dict = data.get("inputs", {})

        print(f"📥 Caso {caso_id} recebido ({len(inputs_dict)} inputs)")

        
        # Verificar se Aspen está vivo
        try:
            _ = aspen.Visible
        except:
            logger.warning("Aspen travado — reconectando...")
            try:
                aspen = win32.Dispatch('Apwn.Document')
                aspen.InitFromArchive2(str(CAMINHO_ASPEN))
                aspen.Visible = 0
                logger.info("Reconectado!")
            except Exception as e:
                logger.error(f"Falha ao reconectar: {e}")
                falhas += 1
                data["novo_dado"] = False
                escrever_json(ARQUIVO_INPUTS, data)
                continue

        # Simular
        inicio = time.time()
        print(f"   ⚙️  Simulando...", end='\r')

        sucesso = simular(aspen, inputs_dict, inputs_paths)
        tempo   = time.time() - inicio

        if not sucesso:
            logger.error(f"Simulação falhou para caso {caso_id}")
            escrever_json(ARQUIVO_STATUS, {
                "timestamp": datetime.now().isoformat(),
                "caso_id": caso_id,
                "aspen_finalizado": False,
                "erro": "Simulação falhou"
            })
            data["novo_dado"] = False
            escrever_json(ARQUIVO_INPUTS, data)
            falhas += 1
            continue

        # Coletar outputs
        outputs = {}
        for var_name, path in outputs_paths.items():
            info  = outputs_info[var_name]
            value = ler_output(aspen, path, info, componentes_lista)

            # Converter W → kW para variáveis de energia
            if value is not None and any(x in var_name.upper() for x in ['WNET', 'QCALC', 'DUTY']):
                try:
                    value = float(value) / 1000
                except:
                    pass

            outputs[var_name] = value

        outputs_validos = sum(1 for v in outputs.values() if v is not None)
        contador += 1

        print(f"   ✅ Caso {caso_id} — {tempo:.1f}s — {outputs_validos}/{len(outputs_paths)} outputs")

        # Escrever status
        escrever_json(ARQUIVO_STATUS, {
            "timestamp": datetime.now().isoformat(),
            "caso_id": caso_id,
            "aspen_finalizado": True,
            "tempo_simulacao": tempo,
            "outputs": outputs,
            "outputs_validos": outputs_validos,
            "sucesso_coleta": outputs_validos >= len(outputs_paths) * 0.5
        })

        # Limpar flag
        data["novo_dado"] = False
        escrever_json(ARQUIVO_INPUTS, data)

        time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário")
        break

    except Exception as e:
        logger.error(f"Erro no loop: {e}", exc_info=True)
        time.sleep(1)

# ═══════════════════════════════════════════════════════════════════════════
# FINALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  Simulações: {contador}  |  Falhas: {falhas}")

try:
    aspen.Close()
    logger.info("Aspen fechado")
except:
    pass

print("✅ Módulo Aspen V3.0 finalizado")