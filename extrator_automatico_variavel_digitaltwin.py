"""
════════════════════════════════════════════════════════════════════════════════
    EXTRATOR SINCRONIZADO - Gera Configuração Alinhada ao Modelo Treinado
    
    VERSÃO 2.0 - Integrado com config.yaml
    
    DIFERENÇA CRÍTICA:
    Em vez de ler o CSV e chutar os outputs, ele lê o 'config_final.json'
    gerado pelo treinamento. Isso garante que:
    1. A ordem dos inputs seja idêntica.
    2. A lista de outputs seja EXATAMENTE a que o modelo aprendeu.
    3. Usa as configurações centralizadas do config.yaml
════════════════════════════════════════════════════════════════════════════════
"""

import json
import numpy as np
import pandas as pd
from tensorflow import keras
import os
import sys
from pathlib import Path
from datetime import datetime
import yaml

# ═══════════════════════════════════════════════════════════════════════════
# 🔧 CARREGAMENTO DE CONFIGURAÇÕES (YAML)
# ═══════════════════════════════════════════════════════════════════════════

# 1. Identificar a Raiz do Projeto Automaticamente
# Se o script está em: DigitalTwin/scripts/extrator_config.py
# .parent = scripts
# .parent.parent = DigitalTwin (Raiz)
BASE_DIR = Path(__file__).resolve().parent.parent

print(f"📂 Raiz do Projeto detectada: {BASE_DIR}")

# 2. Carregar o arquivo YAML
config_path = BASE_DIR / "config" / "config.yaml"

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    print("✅ Configurações YAML carregadas com sucesso!")
except FileNotFoundError:
    raise FileNotFoundError(f"❌ Arquivo de config não encontrado em: {config_path}")

# 3. Configurar Caminhos (Usando a Raiz + Caminho Relativo do YAML)
PASTA_MODELOS = BASE_DIR / cfg['paths']['output_modelos']
CAMINHO_CONFIG_TREINO = PASTA_MODELOS / "config_final.json"
CAMINHO_SAIDA = PASTA_MODELOS / "config_digital_twin.json"
CAMINHO_DATASET = BASE_DIR / cfg['paths']['dataset']

# 4. Carregar Variáveis Críticas do YAML
VARIAVEIS_CRITICAS = cfg['variables']['critical']
LIMITE_R2_CRITICO = cfg['thresholds']['r2_critical']

print(f"\n📋 Configurações carregadas do YAML:")
print(f"   • Projeto: {cfg['project']['name']} v{cfg['project']['version']}")
print(f"   • Variáveis críticas: {len(VARIAVEIS_CRITICAS)}")
print(f"   • Limiar R² crítico: {LIMITE_R2_CRITICO}")
print(f"   • Dataset: {CAMINHO_DATASET.name}")

# ═══════════════════════════════════════════════════════════════════════════
# 🚀 EXECUÇÃO
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("EXTRATOR SINCRONIZADO v2.0".center(80))
print("="*80 + "\n")

# 1. Carregar configuração do treinamento (A Fonte da Verdade)
print(f"📂 Lendo configuração do treinamento: config_final.json...")

if not CAMINHO_CONFIG_TREINO.exists():
    print(f"❌ ERRO: Arquivo não encontrado: {CAMINHO_CONFIG_TREINO}")
    print("   Execute o script de treinamento ('criar_modelo.py') primeiro.")
    sys.exit(1)

with open(CAMINHO_CONFIG_TREINO, 'r', encoding='utf-8') as f:
    config_treino = json.load(f)

# 2. Extrair Inputs e Outputs exatos
print("🔄 Sincronizando variáveis...")

inputs_exatos = config_treino['inputs']

# O config_final pode salvar outputs como lista de strings ou lista de objetos (dicts)
raw_outputs = config_treino['outputs_individuais']
outputs_exatos = []
outputs_info = {}  # Para armazenar informações adicionais (R², se é crítica, etc.)

if isinstance(raw_outputs[0], dict):
    # Formato novo: [{'nome': 'VAR_A', 'r2': 0.9, 'critica': True}, ...]
    # Importante: Manter a ordem original da lista
    outputs_exatos = [item['nome'] for item in raw_outputs]
    
    # Extrair informações adicionais
    for item in raw_outputs:
        outputs_info[item['nome']] = {
            'r2': item.get('r2', 0.0),
            'critica': item.get('critica', False),
            'aprovado': item.get('aprovado', False),
            'tem_especialista': item.get('retreinamento', {}).get('foi_retreinado', False)
        }
else:
    # Formato antigo: ['VAR_A', 'VAR_B']
    outputs_exatos = raw_outputs
    # Sem informações adicionais disponíveis
    outputs_info = {nome: {'r2': 0.0, 'critica': False, 'aprovado': True, 'tem_especialista': False} 
                    for nome in outputs_exatos}

print(f"   ✅ Inputs detectados: {len(inputs_exatos)}")
print(f"   ✅ Outputs do modelo: {len(outputs_exatos)}")

# 3. Verificar variáveis críticas
print(f"\n🔍 Verificando variáveis críticas configuradas no YAML...")
criticas_encontradas = []
criticas_nao_encontradas = []

for var_critica in VARIAVEIS_CRITICAS:
    if var_critica in outputs_exatos:
        criticas_encontradas.append(var_critica)
        print(f"   ✅ {var_critica} - R²: {outputs_info[var_critica]['r2']:.4f}")
    else:
        criticas_nao_encontradas.append(var_critica)
        print(f"   ⚠️ {var_critica} - NÃO ENCONTRADA NO MODELO!")

if criticas_nao_encontradas:
    print(f"\n⚠️ ATENÇÃO: {len(criticas_nao_encontradas)} variável(is) crítica(s) não encontrada(s)!")
    print("   Elas foram removidas durante o treinamento por baixa qualidade.")

# 4. Carregar Dataset Original (Apenas para pegar valores típicos/médios)
print(f"\n📂 Lendo dataset para calcular médias: {CAMINHO_DATASET.name}...")

try:
    df = pd.read_csv(CAMINHO_DATASET)
    
    # Calcular valores típicos (Média)
    valores_tipicos = {}
    valores_min = {}
    valores_max = {}
    valores_std = {}
    
    print("📊 Calculando estatísticas dos inputs...")
    
    for var in inputs_exatos:
        if var in df.columns:
            valores_tipicos[var] = float(df[var].mean())
            valores_min[var] = float(df[var].min())
            valores_max[var] = float(df[var].max())
            valores_std[var] = float(df[var].std())
        else:
            print(f"   ⚠️ Aviso: Input '{var}' não encontrado no CSV. Usando valores padrão.")
            valores_tipicos[var] = 0.0
            valores_min[var] = 0.0
            valores_max[var] = 1.0
            valores_std[var] = 0.0
    
    print(f"   ✅ Estatísticas calculadas para {len(inputs_exatos)} inputs")
            
except Exception as e:
    print(f"❌ Erro ao ler dataset: {e}")
    print("   Definindo valores padrão")
    valores_tipicos = {var: 0.0 for var in inputs_exatos}
    valores_min = {var: 0.0 for var in inputs_exatos}
    valores_max = {var: 1.0 for var in inputs_exatos}
    valores_std = {var: 0.0 for var in inputs_exatos}

# 5. Configurar Limites Críticos (a partir das variáveis críticas do YAML)
print(f"\n⚙️ Configurando limites críticos...")

limites_criticos = {}

for var_critica in criticas_encontradas:
    # Configuração padrão baseada no YAML
    limites_criticos[var_critica] = {
        "tipo": "min",
        "valor": LIMITE_R2_CRITICO,  # Usa o limite do YAML
        "descricao": f"Variável crítica - Mínimo exigido: {LIMITE_R2_CRITICO}",
        "r2_modelo": outputs_info[var_critica]['r2'],
        "tem_especialista": outputs_info[var_critica]['tem_especialista']
    }
    
    print(f"   ✅ {var_critica}: limite mínimo = {LIMITE_R2_CRITICO}")

# Limites específicos personalizados (podem ser editados manualmente aqui)
limites_personalizados = {
    "PRODUTO_ACETA-01_MOLEFRAC_MIXED": {
        "tipo": "min",
        "valor": 0.95,
        "descricao": "Pureza mínima do produto - Especificação crítica",
        "r2_modelo": outputs_info.get("PRODUTO_ACETA-01_MOLEFRAC_MIXED", {}).get('r2', 0.0),
        "tem_especialista": outputs_info.get("PRODUTO_ACETA-01_MOLEFRAC_MIXED", {}).get('tem_especialista', False)
    }
}

# Mesclar limites personalizados
limites_criticos.update(limites_personalizados)

# 6. Extrair informações de especialistas (se existirem)
print(f"\n🤖 Verificando modelos especialistas...")

especialistas_info = []
if 'retreinamentos' in config_treino and 'historico' in config_treino['retreinamentos']:
    historico_retreinos = config_treino['retreinamentos']['historico']
    
    for retreino in historico_retreinos:
        especialistas_info.append({
            'output': retreino['output'],
            'indice': retreino['indice'],
            'r2_inicial': retreino['r2_inicial'],
            'r2_final': retreino['r2_final'],
            'melhoria': retreino['melhoria'],
            'caminho_modelo': retreino['caminho_modelo'],
            'caminho_scaler': retreino['caminho_scaler']
        })
    
    print(f"   ✅ {len(especialistas_info)} especialistas detectados")
else:
    print(f"   ℹ️ Nenhum especialista encontrado")

# 7. Montar Configuração Final para o Runtime
config_runtime = {
    # Informações do projeto
    "projeto": {
        "nome": cfg['project']['name'],
        "versao": cfg['project']['version'],
        "sincronizado_em": datetime.now().isoformat()
    },
    
    # Caminhos dos modelos
    "caminhos": {
        "modelo_base": str(PASTA_MODELOS / "modelo_base.keras"),
        "scaler_X": str(PASTA_MODELOS / "scaler_X.pkl"),
        "scaler_y": str(PASTA_MODELOS / "scaler_y.pkl"),
        "pasta_especialistas": str(PASTA_MODELOS / "especialistas"),
        "dataset_original": str(CAMINHO_DATASET)
    },
    
    # Dimensões do modelo
    "dimensoes": {
        "n_inputs": len(inputs_exatos),
        "n_outputs": len(outputs_exatos),
        "n_especialistas": len(especialistas_info)
    },
    
    # Variáveis (ordem é crítica!)
    "variaveis": {
        "inputs": inputs_exatos,
        "outputs": outputs_exatos
    },
    
    # Informações dos outputs
    "outputs_detalhados": outputs_info,
    
    # Especialistas disponíveis
    "especialistas": especialistas_info,
    
    # Variáveis críticas (do YAML)
    "variaveis_criticas": {
        "lista": criticas_encontradas,
        "nao_encontradas": criticas_nao_encontradas,
        "limites": limites_criticos
    },
    
    # Estatísticas dos inputs
    "estatisticas_inputs": {
        "valores_tipicos": valores_tipicos,
        "valores_min": valores_min,
        "valores_max": valores_max,
        "valores_std": valores_std
    },
    
    # Thresholds do YAML
    "thresholds": {
        "r2_critical": cfg['thresholds']['r2_critical'],
        "r2_normal": cfg['thresholds']['r2_normal'],
        "approval_target": cfg['thresholds']['approval_target']
    },
    
    # Métricas globais do modelo
    "metricas_globais": config_treino.get('resultados_globais', {}),
    
    # Taxa de aprovação
    "aprovacao": config_treino.get('aprovacao', {})
}

# 8. Salvar
print(f"\n💾 Salvando {CAMINHO_SAIDA.name}...")

with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
    json.dump(config_runtime, f, indent=4, ensure_ascii=False)

# 9. Salvar também uma versão YAML (mais legível)
CAMINHO_SAIDA_YAML = PASTA_MODELOS / "config_digital_twin.yaml"
print(f"💾 Salvando também {CAMINHO_SAIDA_YAML.name} (formato YAML)...")

with open(CAMINHO_SAIDA_YAML, 'w', encoding='utf-8') as f:
    yaml.dump(config_runtime, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

# ═══════════════════════════════════════════════════════════════════════════
# 📊 RELATÓRIO FINAL
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("✅ SINCRONIZAÇÃO CONCLUÍDA COM SUCESSO".center(80))
print("="*80)

print(f"\n📋 RESUMO DA CONFIGURAÇÃO GERADA:")
print(f"\n   🎯 MODELO:")
print(f"      • Tipo: {config_treino.get('arquitetura_tipo', 'ResNet')}")
print(f"      • Inputs:  {config_runtime['dimensoes']['n_inputs']}")
print(f"      • Outputs: {config_runtime['dimensoes']['n_outputs']}")
print(f"      • Especialistas: {config_runtime['dimensoes']['n_especialistas']}")

print(f"\n   🔴 VARIÁVEIS CRÍTICAS:")
print(f"      • Configuradas: {len(VARIAVEIS_CRITICAS)}")
print(f"      • Encontradas: {len(criticas_encontradas)}")
if criticas_nao_encontradas:
    print(f"      • Não encontradas: {len(criticas_nao_encontradas)}")

print(f"\n   📊 PERFORMANCE:")
r2_medio = config_runtime['metricas_globais'].get('r2_medio', 0.0)
taxa_aprovacao = config_runtime['aprovacao'].get('geral', {}).get('taxa_pct', 0.0)
print(f"      • R² médio: {r2_medio:.4f}")
print(f"      • Taxa aprovação: {taxa_aprovacao:.1f}%")

print(f"\n   💾 ARQUIVOS GERADOS:")
print(f"      • {CAMINHO_SAIDA.name} (JSON)")
print(f"      • {CAMINHO_SAIDA_YAML.name} (YAML)")

print(f"\n   📂 LOCALIZAÇÃO:")
print(f"      {PASTA_MODELOS}")

print(f"\n{'='*80}")
print("Isso garante compatibilidade total com o modelo treinado.")
print("Use 'config_digital_twin.json' para carregar o predictor em produção.")
print(f"{'='*80}\n")

# ═══════════════════════════════════════════════════════════════════════════
# 🧪 TESTE DE VALIDAÇÃO (OPCIONAL)
# ═══════════════════════════════════════════════════════════════════════════

print("\n" + "="*80)
print("🧪 TESTE DE VALIDAÇÃO".center(80))
print("="*80)

try:
    print("\n🔍 Verificando integridade dos arquivos...")
    
    # Verificar se modelo base existe
    modelo_base_path = Path(config_runtime['caminhos']['modelo_base'])
    if modelo_base_path.exists():
        print(f"   ✅ Modelo base encontrado: {modelo_base_path.name}")
    else:
        print(f"   ❌ Modelo base NÃO encontrado: {modelo_base_path}")
    
    # Verificar scalers
    scaler_x_path = Path(config_runtime['caminhos']['scaler_X'])
    scaler_y_path = Path(config_runtime['caminhos']['scaler_y'])
    
    if scaler_x_path.exists():
        print(f"   ✅ Scaler X encontrado")
    else:
        print(f"   ❌ Scaler X NÃO encontrado")
    
    if scaler_y_path.exists():
        print(f"   ✅ Scaler Y encontrado")
    else:
        print(f"   ❌ Scaler Y NÃO encontrado")
    
    # Verificar especialistas
    pasta_especialistas = Path(config_runtime['caminhos']['pasta_especialistas'])
    if pasta_especialistas.exists():
        arquivos_esp = list(pasta_especialistas.glob("*.keras"))
        print(f"   ✅ Pasta de especialistas: {len(arquivos_esp)} modelos encontrados")
    else:
        print(f"   ⚠️ Pasta de especialistas não encontrada")
    
    print("\n✅ Validação concluída!")
    
except Exception as e:
    print(f"\n⚠️ Erro na validação: {e}")
    print("   Mas a configuração foi salva corretamente.")

print("\n" + "="*80)
print("🚀 PRONTO PARA USO EM PRODUÇÃO!".center(80))
print("="*80 + "\n")