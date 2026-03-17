"""
═══════════════════════════════════════════════════════════════════════════════
    PARALELO.PY - Módulo de Paralelização (CORRIGIDO COM COMPONENTES)
    
    ✅ Sincronizado com código principal
    ✅ Coleta outputs de componentes corretamente
    ✅ Mantém todas as proteções anti-crash
    ✅ 4x mais rápido com 4 instâncias
    
    VERSÃO: 4.0 - Com Suporte Completo a Componentes
    DATA: 2025-11-08
    
    MUDANÇAS:
    - AspenSimulator agora recebe dados_scanner
    - coletar_outputs() identifica e acessa componentes corretamente
    - Salvamento de dados_scanner no config_geral.pkl
    - Execução passa dados_scanner para AspenExecutor
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import pickle
import pandas as pd
import numpy as np
import subprocess
import time
import win32com.client as win32
import win32gui
import win32con
import win32process
import psutil
import threading
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

PASTA_PARALELO = r"C:\DigitalTwin\paralelo_temp"
os.makedirs(PASTA_PARALELO, exist_ok=True)

PASTA_PLANOS = os.path.join(PASTA_PARALELO, "planos")
PASTA_RESULTADOS = os.path.join(PASTA_PARALELO, "resultados")
os.makedirs(PASTA_PLANOS, exist_ok=True)
os.makedirs(PASTA_RESULTADOS, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# CLASSES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════

class WatchdogRecuperacao:
    """Monitor que detecta travamento e força recuperação automática."""
    
    def __init__(self, timeout_segundos=300):
        self.timeout = timeout_segundos
        self.ultimo_heartbeat = time.time()
        self.running = False
        self.thread = None
        self.callback_recuperacao = None
        self.lock = threading.Lock()
        self.instancia_id = 0
    
    def start(self, callback_recuperacao, instancia_id=0):
        self.instancia_id = instancia_id
        self.callback_recuperacao = callback_recuperacao
        self.running = True
        self.ultimo_heartbeat = time.time()
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print(f"[Inst] 🐕 Watchdog ATIVADO (timeout: {self.timeout}s)")
    
    def heartbeat(self):
        with self.lock:
            self.ultimo_heartbeat = time.time()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _monitor_loop(self):
        logger = logging.getLogger(f"Instancia{self.instancia_id}")
        ultima_checagem = time.time()
        
        while self.running:
            time.sleep(10)
            
            with self.lock:
                tempo_sem_resposta = time.time() - self.ultimo_heartbeat
            
            if tempo_sem_resposta > 60 and (time.time() - ultima_checagem) > 60:
                logger.warning(f"Watchdog: {tempo_sem_resposta/60:.1f} min desde último heartbeat")
                ultima_checagem = time.time()
            
            if tempo_sem_resposta > self.timeout:
                logger.critical("="*80)
                logger.critical("🚨 TRAVAMENTO DETECTADO PELO WATCHDOG!")
                logger.critical(f"⏱️  Sem resposta há {tempo_sem_resposta/60:.1f} minutos")
                logger.critical("🔄 Forçando recuperação automática...")
                logger.critical("="*80)
                
                if self.callback_recuperacao:
                    try:
                        self.callback_recuperacao()
                        logger.info("✅ Callback de recuperação executado")
                    except Exception as e:
                        logger.error(f"❌ Erro no callback: {e}", exc_info=True)
                
                with self.lock:
                    self.ultimo_heartbeat = time.time()


class PopupKiller:
    """Monitor que fecha popups do Aspen automaticamente."""
    
    def __init__(self):
        self.running = False
        self.thread = None
        self.popups_fechados = 0
        self.lock = threading.Lock()
        self.pids_aspen = set()
        
    def start(self):
        if not self.running:
            self._atualizar_pids_aspen()
            self.running = True
            self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.thread.start()
            print(f"[Inst] 🛡️  Monitor anti-popup ATIVADO (PIDs Aspen: {self.pids_aspen})")
    
    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
    
    def _atualizar_pids_aspen(self):
        self.pids_aspen.clear()
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                nome = proc.info['name'].lower()
                if any(x in nome for x in ['aspen', 'apwn']):
                    self.pids_aspen.add(proc.info['pid'])
            except:
                pass
    
    def _monitor_loop(self):
        while self.running:
            try:
                self._atualizar_pids_aspen()
                self._fechar_popups_aspen()
                time.sleep(0.5)
            except:
                pass
    
    def _fechar_popups_aspen(self):
        def callback(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid not in self.pids_aspen:
                        return True
                except:
                    return True
                
                titulo = win32gui.GetWindowText(hwnd)
                keywords = ['aspen', 'error', 'unexpected', 'warning', 'aspen plus']
                
                if any(kw in titulo.lower() for kw in keywords):
                    def encontrar_botao(hwnd_child, _):
                        try:
                            texto = win32gui.GetWindowText(hwnd_child)
                            classe = win32gui.GetClassName(hwnd_child)
                            
                            if 'button' in classe.lower():
                                texto_upper = texto.upper()
                                botoes_validos = ['OK', '&OK', 'YES', '&YES', 'CLOSE', '&CLOSE']
                                
                                if any(btn in texto_upper for btn in botoes_validos):
                                    win32gui.SetForegroundWindow(win32gui.GetParent(hwnd_child))
                                    time.sleep(0.1)
                                    win32gui.PostMessage(hwnd_child, win32con.BM_CLICK, 0, 0)
                                    
                                    with self.lock:
                                        self.popups_fechados += 1
                                    
                                    return False
                        except:
                            pass
                        return True
                    
                    win32gui.EnumChildWindows(hwnd, encontrar_botao, None)
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except:
                pass
            return True
        
        try:
            win32gui.EnumWindows(callback, None)
        except:
            pass


def limpar_arquivos_temporarios_recursivo(caminho_projeto: str) -> int:
    """Limpa arquivos temporários."""
    import glob
    
    padroes = ['*.dmp', '*.tmp', '*ProcessDump*.dmp']
    removidos = 0
    
    for padrao in padroes:
        try:
            arquivos = glob.glob(os.path.join(caminho_projeto, '**', padrao), recursive=True)
            for arquivo in arquivos:
                try:
                    os.remove(arquivo)
                    removidos += 1
                except:
                    pass
        except:
            pass
    
    return removidos


def matar_processos_aspen() -> int:
    """Mata processos do Aspen."""
    mortos = 0
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            nome = proc.info['name'].lower()
            if any(x in nome for x in ['aspen', 'apwn']):
                proc.kill()
                mortos += 1
        except:
            pass
    
    if mortos > 0:
        time.sleep(3)
    return mortos

# ═══════════════════════════════════════════════════════════════════════════
# CLASSES ASPEN (SINCRONIZADAS COM CÓDIGO PRINCIPAL)
# ═══════════════════════════════════════════════════════════════════════════

class AspenConnection:
    """Gerencia conexão COM com Aspen."""
    
    def __init__(self, caminho_aspen: str):
        self.caminho_aspen = caminho_aspen
        self.aspen = None
    
    def conectar(self) -> bool:
        print(f"[Inst] ⏳ Conectando ao Aspen...")
        
        for tentativa in range(3):
            try:
                self.aspen = win32.Dispatch('Apwn.Document')
                self.aspen.InitFromArchive2(self.caminho_aspen)
                self.aspen.Visible = 0
                print(f"[Inst]    ✅ Conectado!\n")
                return True
            except Exception as e:
                if tentativa < 2:
                    time.sleep(5)
                else:
                    print(f"[Inst]    ❌ Erro: {e}\n")
                    return False
        return False
    
    def verificar_vivo(self) -> bool:
        try:
            _ = self.aspen.Visible
            return True
        except:
            return False
    
    def fechar(self):
        try:
            if self.aspen:
                self.aspen.Close()
                time.sleep(1)
        except:
            pass
        self.aspen = None


class AspenValidator:
    """Valida valores antes de enviar ao Aspen."""
    
    @staticmethod
    def validar_valor(var_name: str, value: float) -> Tuple[float, bool, Optional[str]]:
        try:
            valor_float = float(value)
            corrigido = False
            
            var_upper = var_name.upper()
            is_estrutura = any(x in var_upper for x in ['NSTAGE', 'FEED_STAGE', 'STAGE'])
            is_temp = any(x in var_upper for x in ['TEMP', 'TEMPERATURE', '_T'])
            is_basis = 'BASIS' in var_upper
            is_rr = any(x in var_upper for x in ['RR', 'RATIO', 'REFLUX'])
            is_flow = any(x in var_upper for x in ['FLOW', 'MOLE', 'MASS', 'RATE'])
            
            if abs(valor_float) < 1e-15:
                if is_estrutura:
                    valor_float = 2.0
                elif is_temp:
                    valor_float = 25.0
                elif is_basis or is_rr:
                    valor_float = 0.5
                elif is_flow:
                    valor_float = 1e-5
                else:
                    valor_float = 1e-10
                corrigido = True
            
            elif is_estrutura and valor_float < 2:
                valor_float = 2.0
                corrigido = True
            
            elif abs(valor_float) > 1e10:
                valor_float = 1e10 if valor_float > 0 else -1e10
                corrigido = True
            
            elif not np.isfinite(valor_float):
                if is_estrutura:
                    valor_float = 10.0
                elif is_temp:
                    valor_float = 25.0
                else:
                    valor_float = 1e-10
                corrigido = True
            
            elif (is_basis or is_rr) and valor_float < 0:
                valor_float = abs(valor_float) if abs(valor_float) > 1e-15 else 0.5
                corrigido = True
            
            return valor_float, corrigido, None
        
        except Exception as e:
            return 1e-10, True, str(e)


class AspenSimulator:
    """Executa simulações no Aspen (SINCRONIZADO COM CÓDIGO PRINCIPAL)."""
    
    def __init__(self, connection, inputs_paths, outputs_paths, dados_scanner, reinit_config):
        """
        Args:
            connection: AspenConnection
            inputs_paths: Dict de paths dos inputs
            outputs_paths: Dict de paths dos outputs
            dados_scanner: Dict completo do scanner (NOVO!)
            reinit_config: Config de reinit
        """
        self.connection = connection
        self.validator = AspenValidator()
        self.inputs_paths = inputs_paths
        self.outputs_paths = outputs_paths
        self.dados_scanner = dados_scanner  # ✅ ADICIONADO!
        self.reinit_config = reinit_config
        self.contador_sim = 0
        self.inputs_inteiros = []
        self.regras_dependencia = {}
    
    def aplicar_regras_inteiras(self, valores_dict: Dict) -> Dict:
        valores_corrigidos = valores_dict.copy()
        for var_name in self.inputs_inteiros:
            if var_name in valores_corrigidos:
                valor_int = int(round(valores_corrigidos[var_name]))
                if any(x in var_name.upper() for x in ['NSTAGE', 'FEED_STAGE', 'STAGE']):
                    valor_int = max(2, valor_int)
                valores_corrigidos[var_name] = valor_int
        return valores_corrigidos
    
    def aplicar_regras_dependencia(self, valores_dict: Dict) -> Dict:
        valores_corrigidos = valores_dict.copy()
        for var_name, regra in self.regras_dependencia.items():
            if var_name in valores_corrigidos and regra['tipo'] == 'menor_igual':
                var_mae = regra['variavel_mae']
                if var_mae in valores_corrigidos:
                    nstage = int(valores_corrigidos[var_mae])
                    feed = int(valores_corrigidos[var_name])
                    
                    if feed >= nstage:
                        valores_corrigidos[var_name] = max(1, nstage - 1)
                    elif feed < 1:
                        valores_corrigidos[var_name] = 1
        return valores_corrigidos
    
    def setar_inputs(self, valores_dict: Dict, 
                    variaveis_bloqueadas_estrutura: Optional[Dict] = None) -> Tuple[bool, List[str]]:
        erros = []
        
        try:
            valores_validados = {}
            for var_name, value in valores_dict.items():
                valor_validado, corrigido, erro = self.validator.validar_valor(var_name, value)
                if erro:
                    erros.append(f"{var_name}: {erro}")
                    continue
                valores_validados[var_name] = valor_validado
            
            if not valores_validados:
                return False, ["Nenhum valor válido"]
            
            valores_validados = self.aplicar_regras_inteiras(valores_validados)
            valores_validados = self.aplicar_regras_dependencia(valores_validados)
            
            valores_a_setar = {}
            if variaveis_bloqueadas_estrutura:
                for var_name, value in valores_validados.items():
                    if var_name not in variaveis_bloqueadas_estrutura:
                        valores_a_setar[var_name] = value
            else:
                valores_a_setar = valores_validados
            
            if not valores_a_setar:
                return True, []
            
            mudou_estrutura = False
            
            for var_name, value in valores_a_setar.items():
                try:
                    if var_name not in self.inputs_paths:
                        continue
                    
                    caminho = self.inputs_paths[var_name]
                    node = self.connection.aspen.Tree.FindNode(caminho)
                    
                    if node:
                        node.Value = float(value)
                        
                        if 'NSTAGE' in var_name or 'FEED_STAGE' in var_name:
                            mudou_estrutura = True
                        
                        if 'FEED_STAGE' in var_name and mudou_estrutura:
                            try:
                                self.connection.aspen.Engine.Reinit()
                                time.sleep(0.5)
                                mudou_estrutura = False
                            except:
                                pass
                except Exception as e:
                    erros.append(f"{var_name}: {str(e)[:80]}")
            
            sucesso = len(erros) < len(valores_a_setar) * 0.2
            return sucesso, erros
        
        except Exception as e:
            return False, [f"Erro fatal: {str(e)[:100]}"]
    
    def precisa_reinit(self) -> bool:
        tipo = self.reinit_config['tipo']
        if tipo == 1:
            return False
        elif tipo == 2:
            return True
        elif tipo == 3:
            return self.contador_sim % self.reinit_config['intervalo'] == 0
        elif tipo == 4:
            return self.contador_sim == 0
        return False
    
    def executar_simulacao(self) -> Tuple[bool, Optional[str]]:
        try:
            if self.precisa_reinit():
                try:
                    self.connection.aspen.Engine.Reinit()
                    time.sleep(1)
                except:
                    pass
            
            try:
                status = self.connection.aspen.Engine.Run2()
                time.sleep(0.5)
                self.contador_sim += 1
                
                if status == 0 or status is None:
                    return True, None
                else:
                    return False, f"Status {status}"
            except Exception as e:
                self.contador_sim += 1
                return False, f"Erro: {str(e)[:100]}"
        
        except Exception as e:
            self.contador_sim += 1
            return False, f"Erro: {str(e)[:100]}"
    
    def coletar_outputs(self) -> Tuple[Dict, bool, List[str]]:
        """
        ✅ FUNÇÃO CORRIGIDA - Sincronizada com código principal
        Coleta outputs com suporte a componentes.
        """
        outputs = {}
        erros = []
        
        try:
            for var_name, path in self.outputs_paths.items():
                try:
                    node = self.connection.aspen.Tree.FindNode(path)
                    
                    if not node:
                        outputs[var_name] = None
                        erros.append(f"{var_name}: Nó não encontrado")
                        continue
                    
                    # ✅ Buscar info do scanner
                    info_output = self.dados_scanner['caminhos_com_valores']['OUTPUTS'].get(var_name, {})
                    value = None
                    
                    # ✅ Verificar se é output de componente
                    if 'componente' in info_output:
                        componente = info_output['componente']
                        try:
                            # ✅ Sintaxe correta
                            value = node.Elements(componente).Value
                        except Exception as e:
                            # Fallback 1: Array
                            try:
                                value = node.Value[componente] if hasattr(node.Value, '__getitem__') else None
                            except:
                                # Fallback 2: Índice numérico
                                try:
                                    idx = list(self.dados_scanner.get('componentes', {}).keys()).index(componente)
                                    value = node.Value[idx] if hasattr(node.Value, '__getitem__') else None
                                except:
                                    value = None
                    else:
                        # Output normal (não-componente)
                        try:
                            value = node.Value
                            
                            # Tratar vetores (pegar primeiro elemento se for array)
                            if hasattr(value, '__len__') and not isinstance(value, str):
                                if len(value) > 0:
                                    value = float(value[0])
                                else:
                                    value = None
                        except:
                            value = None
                    
                    # Conversão de unidades (duty em kW)
                    if value is not None:
                        if any(x in var_name.upper() for x in ['WNET', 'QCALC', 'DUTY', 'QCOND', 'QREB']):
                            try:
                                value = float(value) / 1000
                            except:
                                pass
                    
                    # Validação
                    if value is not None:
                        try:
                            value_float = float(value)
                            if not np.isfinite(value_float):
                                value = None
                                erros.append(f"{var_name}: Valor inválido (NaN/Inf)")
                            else:
                                value = value_float
                        except (ValueError, TypeError):
                            value = None
                            erros.append(f"{var_name}: Não conversível para float")
                    
                    outputs[var_name] = value
                
                except Exception as e:
                    outputs[var_name] = None
                    erros.append(f"{var_name}: {str(e)[:50]}")
            
            # Validação de sucesso (50% mínimo)
            outputs_validos = sum(1 for v in outputs.values() if v is not None)
            total_outputs = len(self.outputs_paths)
            
            if outputs_validos == 0:
                sucesso = False
            elif outputs_validos >= total_outputs * 0.5:
                sucesso = True
            else:
                sucesso = False
            
            return outputs, sucesso, erros
        
        except Exception as e:
            outputs_nulos = {k: None for k in self.outputs_paths.keys()}
            return outputs_nulos, False, [f"Erro: {str(e)[:100]}"]


class AspenExecutor:
    """Executor completo com sistema anti-crash."""
    
    def __init__(self, caminho_aspen: str, inputs_paths: Dict, 
                 outputs_paths: Dict, dados_scanner: Dict, reinit_config: Dict, instancia_id: int = 0):
        """
        Args:
            caminho_aspen: Path do arquivo .apw
            inputs_paths: Dict de paths dos inputs
            outputs_paths: Dict de paths dos outputs
            dados_scanner: Dict completo do scanner (NOVO!)
            reinit_config: Config de reinit
            instancia_id: ID da instância
        """
        self.connection = AspenConnection(caminho_aspen)
        self.simulator = AspenSimulator(
            self.connection, inputs_paths, outputs_paths, 
            dados_scanner,  # ✅ ADICIONADO!
            reinit_config
        )
        self.popup_killer = PopupKiller()
        self.watchdog = WatchdogRecuperacao(timeout_segundos=300)
        self.crashes_recuperados = 0
        self.casos_falhados = {}
        self.max_tentativas_por_caso = 3
        self.instancia_id = instancia_id
    
    def conectar(self) -> bool:
        logger = logging.getLogger(f"Instancia{self.instancia_id}")
        logger.info("Tentando conectar ao Aspen...")
        
        sucesso = self.connection.conectar()
        if sucesso:
            logger.info("✅ Conexão estabelecida")
            self.popup_killer.start()
            logger.info("✅ PopupKiller iniciado")
            
            def callback_recuperacao():
                logger.critical("🚑 Executando recuperação de emergência...")
                self._forcar_recuperacao()
            
            self.watchdog.start(callback_recuperacao, self.instancia_id)
            logger.info("✅ Watchdog iniciado")
        else:
            logger.error("❌ Falha na conexão")
        
        return sucesso
    
    def _forcar_recuperacao(self):
        logger = logging.getLogger(f"Instancia{self.instancia_id}")
        
        logger.info("1️⃣  Matando processos Aspen...")
        matar_processos_aspen()
        
        logger.info("2️⃣  Aguardando 10 segundos...")
        time.sleep(10)
        
        logger.info("3️⃣  Tentando reconectar...")
        try:
            self.connection.fechar()
        except:
            pass
        
        if self.connection.conectar():
            logger.info("✅ Reconectado com sucesso!")
        else:
            logger.error("❌ Falha na reconexão")
    
    def executar_caso_com_recuperacao(self, caso_id: int, inputs: Dict, 
                                      vars_bloq_estrut: Optional[Dict] = None) -> Tuple[Optional[Dict], Optional[List], bool, Optional[str]]:
        
        logger = logging.getLogger(f"Instancia{self.instancia_id}")
        logger.debug(f"Caso {caso_id}: Início")
        
        self.watchdog.heartbeat()
        
        if caso_id in self.casos_falhados:
            if self.casos_falhados[caso_id] >= self.max_tentativas_por_caso:
                logger.warning(f"Caso {caso_id}: Pulado após {self.max_tentativas_por_caso} tentativas")
                return None, None, False, f"Pulado"
        
        tent_atual = self.casos_falhados.get(caso_id, 0)
        
        try:
            self.watchdog.heartbeat()
            
            if not self.connection.verificar_vivo():
                logger.error(f"Caso {caso_id}: Aspen travado detectado")
                
                if self._tentar_recuperacao_completa():
                    logger.info(f"Caso {caso_id}: Recuperação OK, retentando...")
                    self.casos_falhados[caso_id] = tent_atual + 1
                    
                    if tent_atual < self.max_tentativas_por_caso - 1:
                        return self.executar_caso_com_recuperacao(caso_id, inputs, vars_bloq_estrut)
                
                return None, None, False, "Aspen travado"
            
            self.watchdog.heartbeat()
            ok_setar, erros_setar = self.simulator.setar_inputs(inputs, vars_bloq_estrut)
            
            if not ok_setar:
                self.casos_falhados[caso_id] = tent_atual + 1
                logger.warning(f"Caso {caso_id}: Falha setagem")
                return None, None, False, f"Falha setagem"
            
            self.watchdog.heartbeat()
            ok_sim, erro_sim = self.simulator.executar_simulacao()
            
            if not ok_sim:
                logger.warning(f"Caso {caso_id}: Simulação falhou")
                
                self.watchdog.heartbeat()
                if not self.connection.verificar_vivo():
                    logger.error(f"Caso {caso_id}: Aspen travou durante simulação")
                    
                    if self._tentar_recuperacao_completa():
                        logger.info(f"Caso {caso_id}: Recuperação pós-simulação OK")
                        self.casos_falhados[caso_id] = tent_atual + 1
                        
                        if tent_atual < self.max_tentativas_por_caso - 1:
                            return self.executar_caso_com_recuperacao(caso_id, inputs, vars_bloq_estrut)
                
                self.casos_falhados[caso_id] = tent_atual + 1
                return None, None, False, f"Não convergiu"
            
            self.watchdog.heartbeat()
            outputs, ok_coleta, erros_coleta = self.simulator.coletar_outputs()
            
            if not ok_coleta:
                self.casos_falhados[caso_id] = tent_atual + 1
                logger.warning(f"Caso {caso_id}: Outputs insuficientes")
                return outputs, erros_coleta, False, f"Outputs insuficientes"
            
            if caso_id in self.casos_falhados:
                del self.casos_falhados[caso_id]
            
            self.watchdog.heartbeat()
            logger.debug(f"Caso {caso_id}: Sucesso")
            return outputs, None, True, None
            
        except Exception as e:
            self.casos_falhados[caso_id] = tent_atual + 1
            logger.error(f"Caso {caso_id}: Exceção - {e}", exc_info=True)
            return None, None, False, f"Erro: {str(e)[:100]}"
    
    def _tentar_recuperacao_completa(self) -> bool:
        logger = logging.getLogger(f"Instancia{self.instancia_id}")
        
        logger.info("="*70)
        logger.info("🚑 RECUPERAÇÃO COMPLETA")
        logger.info("="*70)
        
        try:
            logger.info("1️⃣  Fechando conexão atual...")
            self.connection.fechar()
        except Exception as e:
            logger.warning(f"Erro ao fechar: {e}")
        
        logger.info("2️⃣  Matando processos Aspen...")
        mortos = matar_processos_aspen()
        logger.info(f"   ⚔️  {mortos} processo(s) morto(s)")
        
        logger.info("3️⃣  Limpando arquivos temporários...")
        try:
            config_path = os.path.join(PASTA_PARALELO, "config_geral.pkl")
            with open(config_path, 'rb') as f:
                config = pickle.load(f)
            
            caminho_projeto = config.get('caminho_projeto', '')
            if caminho_projeto:
                removidos = limpar_arquivos_temporarios_recursivo(caminho_projeto)
                logger.info(f"   🧹 {removidos} arquivo(s) removido(s)")
        except Exception as e:
            logger.warning(f"Limpeza falhou: {e}")
        
        logger.info("4️⃣  Aguardando 10 segundos...")
        time.sleep(10)
        
        logger.info("5️⃣  Tentando reconectar...")
        if self.connection.conectar():
            logger.info("✅ Reconexão bem-sucedida!")
            self.crashes_recuperados += 1
            self.popup_killer.start()
            logger.info("✅ PopupKiller reiniciado")
            return True
        else:
            logger.error("❌ Reconexão falhou!")
            return False
    
    def fechar(self):
        self.watchdog.stop()
        self.popup_killer.stop()
        self.connection.fechar()
        matar_processos_aspen()

# ═══════════════════════════════════════════════════════════════════════════
# PREPARAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def dividir_plano(df_plano: pd.DataFrame, num_instancias: int = 4) -> List[pd.DataFrame]:
    """Divide plano experimental em N partes."""
    total_casos = len(df_plano)
    casos_por_instancia = total_casos // num_instancias
    
    planos = []
    for i in range(num_instancias):
        inicio = i * casos_por_instancia
        fim = total_casos if i == num_instancias - 1 else (i + 1) * casos_por_instancia
        planos.append(df_plano.iloc[inicio:fim].copy())
    
    return planos


def salvar_planos(planos: List[pd.DataFrame]) -> List[Dict]:
    """Salva planos divididos."""
    distribuicao = []
    
    for i, plano in enumerate(planos, 1):
        caminho = os.path.join(PASTA_PLANOS, f"plano_instancia_{i}.pkl")
        plano.to_pickle(caminho)
        
        info = {
            'instancia': i,
            'n_casos': len(plano),
            'id_inicio': int(plano['ID'].min()),
            'id_fim': int(plano['ID'].max()),
            'plano_path': caminho
        }
        distribuicao.append(info)
        print(f"   ✅ Instância {i}: {len(plano):>6,} casos (IDs {info['id_inicio']}-{info['id_fim']})")
    
    return distribuicao


def salvar_configuracao_geral(
    dados_scanner: Dict,
    inputs_paths: Dict,
    outputs_paths: Dict,
    config_experimento: Dict,
    config_limites: Dict = None,
    config_estrutura_torre: Dict = None,
    variaveis_bloqueadas: Optional[Dict] = None,
    variaveis_estrutura_bloqueadas: Optional[Dict] = None,
    distribuicao: Optional[List[Dict]] = None,
    pasta_saida: Optional[str] = None
):
    """
    ✅ FUNÇÃO CORRIGIDA - Agora salva dados_scanner completo
    """
    config = {
        'arquivo_aspen': dados_scanner['arquivo'],
        'caminho_projeto': os.path.dirname(dados_scanner['arquivo']),
        'pasta_saida': pasta_saida or r"C:\DigitalTwin\2_datasets_gerados",
        'inputs_paths': inputs_paths,
        'outputs_paths': outputs_paths,
        'dados_scanner': dados_scanner,  # ✅ ADICIONADO!
        'reinit_config': config_experimento['reinit'],
        'backup_intervalo': config_experimento['backup_intervalo'],
        'config_limites': config_limites or {},
        'config_estrutura_torre': config_estrutura_torre or {},
        'variaveis_bloqueadas': variaveis_bloqueadas or {},
        'variaveis_estrutura_bloqueadas': variaveis_estrutura_bloqueadas or {},
        'distribuicao': distribuicao or [],
        'timestamp': datetime.now().isoformat()
    }
    
    caminho = os.path.join(PASTA_PARALELO, "config_geral.pkl")
    with open(caminho, 'wb') as f:
        pickle.dump(config, f)
    
    print(f"   ✅ Configuração geral salva\n")
    return caminho

# ═══════════════════════════════════════════════════════════════════════════
# EXECUÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def executar_paralelo_automatico(script_gerador: str, num_instancias: int = 4):
    """Abre terminais automaticamente."""
    print(f"\n{'='*80}")
    print(f"🚀 INICIANDO {num_instancias} INSTÂNCIAS".center(80))
    print(f"{'='*80}\n")
    
    for i in range(1, num_instancias + 1):
        comando = f'start cmd /k "python {script_gerador} --instancia {i}"'
        subprocess.Popen(comando, shell=True)
        print(f"   ✅ Terminal {i} aberto")
        time.sleep(2)
    
    print(f"\n✅ {num_instancias} terminais abertos!\n")
    print(f"{'─'*80}")
    print("💡 Aguarde todas finalizarem, depois execute:")
    print(f"   python {os.path.basename(script_gerador)} --combinar")
    print(f"{'─'*80}\n")


def executar_instancia(instancia_id: int):
    """
    ✅ FUNÇÃO ATUALIZADA COM RESUME AUTOMÁTICO
    """
    # Configuração de Logging
    log_path = os.path.join(PASTA_PARALELO, f"instancia_{instancia_id}.log")
    logger = logging.getLogger(f"Instancia{instancia_id}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, mode='a', encoding='utf-8') # Mode 'a' para não apagar log antigo
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

    print(f"\n{'='*80}")
    print(f"INSTÂNCIA {instancia_id} (MODO RESUME)".center(80))
    print(f"{'='*80}\n")

    # Carrega configs
    config_path = os.path.join(PASTA_PARALELO, "config_geral.pkl")
    if not os.path.exists(config_path):
        logger.error("Configuração não encontrada")
        return
    try:
        with open(config_path, 'rb') as f:
            config = pickle.load(f)
    except:
        return

    # Carrega plano original
    plano_path = os.path.join(PASTA_PLANOS, f"plano_instancia_{instancia_id}.pkl")
    try:
        df_plano = pd.read_pickle(plano_path)
    except:
        return

    # ==============================================================================
    # 🔄 LÓGICA DE RETOMADA (RESUME)
    # ==============================================================================
    resultados = []
    ids_ja_processados = set()
    
    # Procura por backup existente desta instância
    caminho_backup = os.path.join(PASTA_RESULTADOS, f"instancia_{instancia_id}_backup.pkl")
    caminho_final = os.path.join(PASTA_RESULTADOS, f"instancia_{instancia_id}_final.pkl")
    
    # Prioriza carregar o final, se não, carrega o backup
    arquivo_para_carregar = None
    if os.path.exists(caminho_final):
        arquivo_para_carregar = caminho_final
    elif os.path.exists(caminho_backup):
        arquivo_para_carregar = caminho_backup
        
    if arquivo_para_carregar:
        try:
            logger.info(f"Carregando dados existentes de: {os.path.basename(arquivo_para_carregar)}")
            df_existente = pd.read_pickle(arquivo_para_carregar)
            if not df_existente.empty:
                resultados = df_existente.to_dict('records')
                ids_ja_processados = set(df_existente['ID'])
                print(f"♻️  RETOMANDO: {len(ids_ja_processados)} casos já encontrados no disco.")
                logger.info(f"Retomando com {len(ids_ja_processados)} casos prontos")
        except Exception as e:
            logger.error(f"Erro ao carregar backup para resume: {e}")
            print(f"⚠️  Erro ao ler backup, iniciando do zero: {e}")

    # ==============================================================================

    # Cria executor
    try:
        executor = AspenExecutor(
            config['arquivo_aspen'],
            config['inputs_paths'],
            config['outputs_paths'],
            config['dados_scanner'],
            config['reinit_config'],
            instancia_id
        )
    except:
        return

    if not executor.conectar():
        return

    # Configura regras (igual original)
    inputs_inteiros = []
    regras = {}
    for var_name in config['inputs_paths'].keys():
        if any(x in var_name.upper() for x in ['NSTAGE', 'FEED_STAGE', 'STAGE']):
            inputs_inteiros.append(var_name)
        if 'FEED_STAGE' in var_name.upper():
            bloco = var_name.split('_')[0]
            var_nstage = f"{bloco}_NSTAGE"
            if var_nstage in config['inputs_paths']:
                regras[var_name] = {'tipo': 'menor_igual', 'variavel_mae': var_nstage}
    
    executor.simulator.inputs_inteiros = inputs_inteiros
    executor.simulator.regras_dependencia = regras

    # Contadores
    sucessos = len(resultados) # Começa com o que já tem
    falhas = 0
    inicio_total = time.time()

    # Loop Principal
    for idx, row in df_plano.iterrows():
        caso_id = int(row['ID'])
        
        # ⏩ PULA CASOS JÁ FEITOS
        if caso_id in ids_ja_processados:
            continue

        print(f"[Inst {instancia_id}] [{caso_id}/{df_plano['ID'].max()}] ", end="", flush=True)
        
        inicio = time.time()
        inputs = {k: row[k] for k in config['inputs_paths'].keys() if k in row}
        
        try:
            outputs, erros, sucesso, msg_erro = executor.executar_caso_com_recuperacao(
                caso_id, inputs, config['variaveis_estrutura_bloqueadas']
            )
            
            tempo_sim = time.time() - inicio
            
            if sucesso:
                registro = {
                    'ID': caso_id,
                    **inputs, 
                    **outputs,
                    'timestamp': datetime.now().isoformat(),
                    'tempo_simulacao': tempo_sim,
                    'instancia': instancia_id
                }
                resultados.append(registro)
                logger.info(f"✅ Caso {caso_id}: SUCESSO ({tempo_sim:.1f}s)")
                print(f"✅ ({tempo_sim:.1f}s)")
                sucessos += 1
            else:
                logger.warning(f"❌ Caso {caso_id}: FALHA - {msg_erro}")
                print(f"❌ {msg_erro}")
                falhas += 1
        
        except Exception as e:
            logger.error(f"💥 Caso {caso_id}: EXCEÇÃO - {e}", exc_info=True)
            print(f"💥 Exceção")
            falhas += 1
        
        # Backup a cada intervalo
        if config['backup_intervalo'] > 0 and sucessos % config['backup_intervalo'] == 0:
            df_temp = pd.DataFrame(resultados)
            backup_path = os.path.join(PASTA_RESULTADOS, f"instancia_{instancia_id}_backup.pkl")
            df_temp.to_pickle(backup_path)
            logger.info(f"💾 Backup atualizado: {len(resultados)} casos")
            
        # Limpeza preventiva
        if sucessos % 50 == 0 and sucessos > len(ids_ja_processados):
            limpar_arquivos_temporarios_recursivo(config['caminho_projeto'])

    # Fim
    executor.fechar()
    
    # Salva final
    df_final = pd.DataFrame(resultados)
    resultado_path = os.path.join(PASTA_RESULTADOS, f"instancia_{instancia_id}_final.pkl")
    df_final.to_pickle(resultado_path)
    
    verificar_e_combinar_automatico(config, instancia_id)

# ═══════════════════════════════════════════════════════════════════════════
# COMBINAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

def verificar_e_combinar_automatico(config: Dict, instancia_id: int):
    """Verifica se todas finalizaram e combina."""
    try:
        num_instancias = len(config.get('distribuicao', []))
        if num_instancias == 0:
            num_instancias = 4
        
        arquivos_finalizados = []
        for i in range(1, num_instancias + 1):
            path = os.path.join(PASTA_RESULTADOS, f"instancia_{i}_final.pkl")
            if os.path.exists(path):
                arquivos_finalizados.append(path)
        
        print(f"\n{'─'*80}")
        print(f"📊 Status: {len(arquivos_finalizados)}/{num_instancias} instâncias finalizadas")
        print(f"{'─'*80}\n")
        
        if len(arquivos_finalizados) == num_instancias:
            print(f"\n{'='*80}")
            print("🎉 TODAS AS INSTÂNCIAS FINALIZADAS!".center(80))
            print(f"{'='*80}\n")
            print("🔄 Combinando resultados automaticamente...\n")
            
            time.sleep(2)
            
            pasta_saida = config.get('pasta_saida', r"C:\DigitalTwin\2_datasets_gerados")
            df_final = combinar_resultados(pasta_saida, num_instancias)
            
            if df_final is not None:
                print(f"\n{'='*80}")
                print("✅ DATASET COMPLETO GERADO!".center(80))
                print(f"{'='*80}\n")
    
    except Exception as e:
        print(f"\n⚠️  Erro ao combinar: {e}")
        print(f"   Execute manualmente: python gerador_paralelo.py --combinar\n")


def combinar_resultados(pasta_saida: str, num_instancias: int = 4) -> Optional[pd.DataFrame]:
    """
    ✅ FUNÇÃO CORRIGIDA - Trata casos sem coluna ID
    """
    print(f"\n{'='*80}")
    print("COMBINANDO RESULTADOS".center(80))
    print(f"{'='*80}\n")
    
    arquivos = []
    for i in range(1, num_instancias + 1):
        path = os.path.join(PASTA_RESULTADOS, f"instancia_{i}_final.pkl")
        if os.path.exists(path):
            arquivos.append(path)
    
    if not arquivos:
        print("❌ Nenhum resultado encontrado!")
        return None
    
    print(f"📂 {len(arquivos)}/{num_instancias} instância(s):\n")
    
    dfs = []
    for i, arquivo in enumerate(sorted(arquivos), 1):
        df = pd.read_pickle(arquivo)
        dfs.append(df)
        print(f"   ✅ Instância {i}: {len(df):>8,} casos")
    
    df_combinado = pd.concat(dfs, ignore_index=True)
    
    # ✅ Verifica se coluna ID existe
    if 'ID' in df_combinado.columns:
        df_combinado = df_combinado.sort_values('ID').reset_index(drop=True)
    else:
        df_combinado.insert(0, 'ID', range(1, len(df_combinado) + 1))
        print(f"\n⚠️  Coluna 'ID' criada sequencialmente")
    
    print(f"\n📊 Dataset combinado: {len(df_combinado):,} casos")
    print(f"   Colunas: {len(df_combinado.columns)}\n")
    
    # Salva em 3 formatos
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f'dataset_{len(df_combinado)}casos_paralelo_{timestamp}'
    
    print("💾 Salvando dataset final...\n")
    
    # PKL
    pkl_path = os.path.join(pasta_saida, f'{base_name}.pkl')
    df_combinado.to_pickle(pkl_path)
    tamanho_pkl = os.path.getsize(pkl_path) / 1024
    print(f"   ✅ Pickle: {os.path.basename(pkl_path)} ({tamanho_pkl:.1f} KB)")
    
    # CSV
    csv_path = os.path.join(pasta_saida, f'{base_name}.csv')
    df_combinado.to_csv(csv_path, index=False)
    tamanho_csv = os.path.getsize(csv_path) / 1024
    print(f"   ✅ CSV:    {os.path.basename(csv_path)} ({tamanho_csv:.1f} KB)")
    
    # Excel
    try:
        xlsx_path = os.path.join(pasta_saida, f'{base_name}.xlsx')
        df_combinado.to_excel(xlsx_path, index=False, engine='openpyxl')
        tamanho_xlsx = os.path.getsize(xlsx_path) / 1024
        print(f"   ✅ Excel:  {os.path.basename(xlsx_path)} ({tamanho_xlsx:.1f} KB)")
    except Exception as e:
        print(f"   ⚠️  Excel: Falhou ({str(e)[:50]})")
    
    print(f"\n📁 Pasta: {pasta_saida}\n")
    
    return df_combinado