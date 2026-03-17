# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import os
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import re
from tqdm import tqdm
from scipy import stats

# ==============================================================================
# CONFIGURACOES
# ==============================================================================

INPUT_DIR  = Path(r"C:\DigitalTwin\resultados")
OUTPUT_DIR = Path(r"C:\DigitalTwin\resultado_analise")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)

THRESHOLD_MAPE = 0.01
MAX_MAPE = 1000

# ==============================================================================
# FUNCOES AUXILIARES
# ==============================================================================

def validar_dados(df):
    print("\nValidando dados de entrada...")

    colunas_req = ['caso_id', 'descricao', 'variavel', 'keras', 'aspen']
    faltando = [col for col in colunas_req if col not in df.columns]

    if faltando:
        raise ValueError(f"Colunas faltando: {faltando}")

    nan_count = df[['keras', 'aspen']].isna().sum()
    if nan_count.any():
        print("Valores NaN encontrados:")
        for col, count in nan_count.items():
            if count > 0:
                pct = (count / len(df)) * 100
                print(f"   - {col}: {count} ({pct:.2f}%)")

    inf_count = np.isinf(df[['keras', 'aspen']]).sum()
    if inf_count.any():
        print("Valores infinitos encontrados:")
        for col, count in inf_count.items():
            if count > 0:
                print(f"   - {col}: {count}")

    if len(df) < 10:
        raise ValueError(f"Dados insuficientes: apenas {len(df)} registros")

    print(f"Validacao concluida: {len(df):,} registros validos")
    return True


def extrair_porcentagem(descricao):
    """Extrai porcentagem de strings como 'Caso 1 (+-5.0%)' ou similar."""
    match = re.search(r'[+\-]?[+-]?(\d+\.?\d*)%', str(descricao))
    if match:
        return float(match.group(1))
    return None


def listar_csvs_disponiveis():
    csv_files = list(INPUT_DIR.glob("*.csv"))
    if not csv_files:
        print(f"Nenhum arquivo CSV encontrado em {INPUT_DIR}")
        return []

    print("\n" + "="*60)
    print("ARQUIVOS CSV DISPONIVEIS")
    print("="*60)
    for i, file in enumerate(csv_files, 1):
        print(f"{i}. {file.name}")
    print("="*60)
    return csv_files


def selecionar_arquivos(csv_files):
    print("\nSelecione os arquivos para analise:")
    print("   - Digite os numeros separados por virgula (ex: 1,3,5)")
    print("   - Digite 'todos' para selecionar todos os arquivos")

    escolha = input("\nSua escolha: ").strip().lower()

    if escolha == 'todos':
        return csv_files

    try:
        indices = [int(x.strip()) - 1 for x in escolha.split(',')]
        arquivos_selecionados = [csv_files[i] for i in indices if 0 <= i < len(csv_files)]
        return arquivos_selecionados
    except Exception:
        print("Selecao invalida. Usando todos os arquivos.")
        return csv_files


def calcular_metricas_adicionais(grupo):
    keras_vals = grupo['keras'].values
    aspen_vals = grupo['aspen'].values

    mask = ~(np.isnan(keras_vals) | np.isnan(aspen_vals))
    keras_vals = keras_vals[mask]
    aspen_vals = aspen_vals[mask]

    if len(keras_vals) == 0:
        return {
            'RMSE': np.nan, 'MAE': np.nan, 'MAPE': np.nan,
            'SMAPE': np.nan, 'R2': np.nan, 'Bias': np.nan,
            'Max_Erro_Abs': np.nan, 'Min_Erro_Abs': np.nan
        }

    erros     = keras_vals - aspen_vals
    erros_abs = np.abs(erros)

    rmse = np.sqrt(np.mean(erros**2))
    mae  = np.mean(erros_abs)

    mask_valid_mape = (np.abs(aspen_vals) > THRESHOLD_MAPE)
    if mask_valid_mape.sum() > 0:
        mape_vals = np.abs(erros[mask_valid_mape] / aspen_vals[mask_valid_mape]) * 100
        mape_vals = np.clip(mape_vals, 0, MAX_MAPE)
        mape = np.mean(mape_vals[np.isfinite(mape_vals)])
    else:
        mape = np.nan

    numerador   = np.abs(keras_vals - aspen_vals)
    denominador = np.abs(aspen_vals) + np.abs(keras_vals)
    smape_vals  = 200 * numerador / (denominador + 1e-10)
    smape       = np.mean(smape_vals[np.isfinite(smape_vals)])

    ss_res = np.sum(erros**2)
    ss_tot = np.sum((aspen_vals - np.mean(aspen_vals))**2)
    r2     = 1 - (ss_res / (ss_tot + 1e-10)) if ss_tot != 0 else np.nan

    bias = np.mean(erros)

    return {
        'RMSE': rmse, 'MAE': mae, 'MAPE': mape, 'SMAPE': smape,
        'R2': r2, 'Bias': bias,
        'Max_Erro_Abs': np.max(erros_abs),
        'Min_Erro_Abs': np.min(erros_abs)
    }

# ==============================================================================
# ANALISES PRINCIPAIS
# ==============================================================================

def analisar_por_grupo(df, coluna_grupo, label_coluna):
    print(f"\nAnalisando por {label_coluna}...")

    resultados = []
    grupos = sorted(df[coluna_grupo].dropna().unique(), key=str)

    for grupo in tqdm(grupos, desc=f"Processando {label_coluna}"):
        df_g     = df[df[coluna_grupo] == grupo]
        metricas = calcular_metricas_adicionais(df_g)

        resultado = {
            'Grupo':          str(grupo),
            'N_Casos':        df_g['caso_id'].nunique(),
            'N_Pontos':       len(df_g),
            'N_Variaveis':    df_g['variavel'].nunique(),
            'Erro_Abs_Medio': df_g['erro_abs'].mean() if 'erro_abs' in df_g.columns else np.nan,
            'Erro_Abs_Med':   df_g['erro_abs'].median() if 'erro_abs' in df_g.columns else np.nan,
            'Erro_Abs_Std':   df_g['erro_abs'].std() if 'erro_abs' in df_g.columns else np.nan,
            'Erro_Pct_Medio': df_g['erro_pct'].mean() if 'erro_pct' in df_g.columns else np.nan,
            **metricas
        }
        resultados.append(resultado)

    return pd.DataFrame(resultados)


def analisar_por_caso(df):
    print("\nAnalisando por caso individual...")

    resultados = []
    for descricao in tqdm(df['descricao'].unique(), desc="Processando casos"):
        df_caso  = df[df['descricao'] == descricao]
        metricas = calcular_metricas_adicionais(df_caso)

        resultado = {
            'Caso':           descricao,
            'N_Pontos':       len(df_caso),
            'N_Variaveis':    df_caso['variavel'].nunique(),
            'Erro_Abs_Medio': df_caso['erro_abs'].mean() if 'erro_abs' in df_caso.columns else np.nan,
            'Erro_Pct_Medio': df_caso['erro_pct'].mean() if 'erro_pct' in df_caso.columns else np.nan,
            **metricas
        }
        resultados.append(resultado)

    df_resultado = pd.DataFrame(resultados)
    return df_resultado.sort_values('RMSE', ascending=False)


def top_outputs_por_grupo(df, coluna_grupo, n=10):
    print(f"\nIdentificando top {n} melhores e piores outputs por grupo...")

    col_erro = 'erro_abs' if 'erro_abs' in df.columns else None
    if col_erro is None:
        print("Coluna erro_abs nao encontrada. Pulando top outputs.")
        return pd.DataFrame(), pd.DataFrame()

    melhores_lista = []
    piores_lista   = []

    for grupo in sorted(df[coluna_grupo].dropna().unique(), key=str):
        df_g = df[df[coluna_grupo] == grupo].copy()

        colunas_base = ['caso_id', 'descricao', 'variavel', 'keras', 'aspen', 'erro_abs']
        colunas_ok   = [c for c in colunas_base if c in df_g.columns]
        if 'erro_pct' in df_g.columns:
            colunas_ok.append('erro_pct')

        melhores = df_g.nsmallest(n, col_erro)[colunas_ok].copy()
        melhores['Grupo']   = str(grupo)
        melhores['Ranking'] = 'Melhor'
        melhores['Posicao'] = range(1, len(melhores) + 1)
        melhores_lista.append(melhores)

        piores = df_g.nlargest(n, col_erro)[colunas_ok].copy()
        piores['Grupo']   = str(grupo)
        piores['Ranking'] = 'Pior'
        piores['Posicao'] = range(1, len(piores) + 1)
        piores_lista.append(piores)

    df_melhores = pd.concat(melhores_lista, ignore_index=True) if melhores_lista else pd.DataFrame()
    df_piores   = pd.concat(piores_lista,   ignore_index=True) if piores_lista   else pd.DataFrame()

    return df_melhores, df_piores


def diagnosticar_grandes_erros(df):
    print("\nDIAGNOSTICO DE ERROS DE ALTA MAGNITUDE")
    print("="*90)

    if 'erro_abs' not in df.columns:
        print("Coluna erro_abs nao encontrada.")
        return

    resumo = df.groupby('variavel').agg(
        max_erro   =('erro_abs', 'max'),
        media_aspen=('aspen',    'mean'),
        media_keras=('keras',    'mean')
    ).sort_values('max_erro', ascending=False).head(15)

    print(f"{'VARIAVEL':<40} | {'MAX ERRO ABS':<15} | {'MEDIA ASPEN':<20} | {'IMPACTO (%)':<10}")
    print("-" * 90)
    for var, row in resumo.iterrows():
        impacto = (row['max_erro'] / abs(row['media_aspen'])) * 100 if row['media_aspen'] != 0 else 0
        print(f"{var:<40} | {row['max_erro']:<15.2f} | {row['media_aspen']:<20.2f} | {impacto:<9.2f}%")
    print("="*90)


def analisar_recorrencia_top10(df_piores, df_completo, output_dir):
    print("\nAnalisando recorrencia nos Top 10 Piores...")

    if df_piores.empty or 'variavel' not in df_piores.columns:
        print("df_piores vazio ou sem coluna 'variavel'. Pulando.")
        return pd.DataFrame()

    contagem = df_piores['variavel'].value_counts().reset_index()
    contagem.columns = ['Variavel', 'Frequencia_Top10']

    agg_cols = {}
    if 'erro_abs' in df_piores.columns:
        agg_cols['erro_abs'] = 'mean'
    if 'erro_pct' in df_piores.columns:
        agg_cols['erro_pct'] = 'mean'

    if agg_cols:
        stats_df = df_piores.groupby('variavel').agg(agg_cols).reset_index()
        resumo   = contagem.merge(stats_df, left_on='Variavel', right_on='variavel', how='left')
        resumo   = resumo.drop('variavel', axis=1, errors='ignore')
    else:
        resumo = contagem

    valor_medio = df_completo.groupby('variavel')['aspen'].mean().reset_index()
    valor_medio.columns = ['Variavel', 'Valor_Medio_ASPEN']
    resumo = resumo.merge(valor_medio, on='Variavel', how='left')

    sort_cols = ['Frequencia_Top10'] + (['erro_abs'] if 'erro_abs' in resumo.columns else [])
    resumo    = resumo.sort_values(sort_cols, ascending=[False] * len(sort_cols))

    print("\n" + "="*100)
    print("VARIAVEIS MAIS FREQUENTES NO TOP 10 PIORES")
    print("="*100)
    for _, row in resumo.head(15).iterrows():
        linha = f"{row['Variavel']:<35} | Freq: {row['Frequencia_Top10']}"
        if 'erro_abs' in row:
            linha += f" | MAE medio: {row['erro_abs']:.4f}"
        if 'Valor_Medio_ASPEN' in row:
            linha += f" | Valor medio ASPEN: {row['Valor_Medio_ASPEN']:.4f}"
        print(linha)

    caminho_csv = output_dir / 'analise_recorrencia_erros.csv'
    resumo.to_csv(caminho_csv, index=False, encoding='utf-8-sig')
    print(f"\nTabela de recorrencia salva em: {caminho_csv}")

    return resumo


def analisar_variaveis_por_grupo(df, coluna_grupo):
    print("\nAnalisando variaveis por grupo...")

    resultados = []
    grupos = sorted(df[coluna_grupo].dropna().unique(), key=str)

    for grupo in tqdm(grupos, desc="Analisando variaveis"):
        df_g = df[df[coluna_grupo] == grupo]
        for variavel in df_g['variavel'].unique():
            df_var   = df_g[df_g['variavel'] == variavel]
            metricas = calcular_metricas_adicionais(df_var)
            resultado = {
                'Grupo':          str(grupo),
                'Variavel':       variavel,
                'N_Casos':        df_var['caso_id'].nunique(),
                'Erro_Abs_Medio': df_var['erro_abs'].mean() if 'erro_abs' in df_var.columns else np.nan,
                'Erro_Pct_Medio': df_var['erro_pct'].mean() if 'erro_pct' in df_var.columns else np.nan,
                **metricas
            }
            resultados.append(resultado)

    return pd.DataFrame(resultados)

# ==============================================================================
# GRAFICOS
# ==============================================================================

def gerar_graficos(df, df_grupos, coluna_grupo, output_dir):
    print("\nGerando graficos...")

    df_sorted = df_grupos.sort_values('Grupo')
    x_labels  = df_sorted['Grupo'].tolist()

    # 1. RMSE e MAE por grupo
    plt.figure(figsize=(12, 6))
    plt.plot(x_labels, df_sorted['RMSE'], 'o-', linewidth=2, markersize=8, label='RMSE')
    plt.plot(x_labels, df_sorted['MAE'],  's-', linewidth=2, markersize=8, label='MAE')
    plt.xlabel('Grupo', fontsize=12)
    plt.ylabel('Erro', fontsize=12)
    plt.title('Evolucao do Erro por Grupo', fontsize=14, fontweight='bold')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_dir / '1_evolucao_erro_linear.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 2 e 3. Boxplot erro absoluto
    if 'erro_abs' in df.columns:
        grupos_unicos = sorted(df[coluna_grupo].dropna().unique(), key=str)
        dados_box     = [df[df[coluna_grupo] == g]['erro_abs'].values for g in grupos_unicos]
        labels_box    = [str(g) for g in grupos_unicos]

        plt.figure(figsize=(14, 8))
        plt.boxplot(dados_box, labels=labels_box)
        plt.xlabel('Grupo', fontsize=12)
        plt.ylabel('Erro Absoluto', fontsize=12)
        plt.title('Distribuicao de Erro Absoluto por Grupo', fontsize=14, fontweight='bold')
        plt.xticks(rotation=45, ha='right')
        plt.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(output_dir / '2_boxplot_erro_linear.png', dpi=150, bbox_inches='tight')
        plt.close()

        plt.figure(figsize=(14, 8))
        plt.boxplot(dados_box, labels=labels_box)
        plt.yscale('log')
        plt.xlabel('Grupo', fontsize=12)
        plt.ylabel('Erro Absoluto (Log)', fontsize=12)
        plt.title('Distribuicao de Erro Absoluto (Escala Log)', fontsize=14, fontweight='bold')
        plt.xticks(rotation=45, ha='right')
        plt.grid(True, alpha=0.3, which='both', axis='y')
        plt.tight_layout()
        plt.savefig(output_dir / '3_boxplot_erro_LOG.png', dpi=150, bbox_inches='tight')
        plt.close()

    # 4. R2 por grupo
    plt.figure(figsize=(12, 6))
    colors = ['red' if r2 > 0.999 else 'steelblue' for r2 in df_sorted['R2']]
    plt.bar(x_labels, df_sorted['R2'], color=colors, alpha=0.7)
    plt.xlabel('Grupo', fontsize=12)
    plt.ylabel('R2', fontsize=12)
    plt.title('R2 por Grupo', fontsize=14, fontweight='bold')
    plt.ylim(0, 1.05)
    plt.axhline(y=0.9,   color='orange', linestyle='--', label='R2=0.9',   linewidth=2)
    plt.axhline(y=0.999, color='red',    linestyle='--', label='R2=0.999', linewidth=2)
    plt.legend()
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(output_dir / '4_r2_por_grupo.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 5. SMAPE por grupo
    plt.figure(figsize=(12, 6))
    plt.plot(x_labels, df_sorted['SMAPE'], 'o-', linewidth=2, markersize=8, color='coral')
    plt.xlabel('Grupo', fontsize=12)
    plt.ylabel('SMAPE (%)', fontsize=12)
    plt.title('SMAPE por Grupo', fontsize=14, fontweight='bold')
    plt.axhline(y=10, color='green',  linestyle='--', label='10% (Excelente)', alpha=0.7)
    plt.axhline(y=20, color='orange', linestyle='--', label='20% (Bom)',       alpha=0.7)
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / '5_smape_por_grupo.png', dpi=150, bbox_inches='tight')
    plt.close()

    # 6. Scatter keras vs aspen (log-log)
    sample_size = min(5000, len(df))
    df_sample   = df.sample(n=sample_size, random_state=42)
    mask_pos    = (df_sample['aspen'] > 0) & (df_sample['keras'] > 0)
    df_plot     = df_sample[mask_pos]

    if len(df_plot) > 0:
        plt.figure(figsize=(10, 8))
        plt.scatter(df_plot['aspen'], df_plot['keras'], alpha=0.4, s=15)
        plt.xscale('log')
        plt.yscale('log')
        min_v = min(df_plot['aspen'].min(), df_plot['keras'].min())
        max_v = max(df_plot['aspen'].max(), df_plot['keras'].max())
        plt.plot([min_v, max_v], [min_v, max_v], 'r--', lw=2, label='Ideal (y=x)')
        plt.xlabel('Valor ASPEN (Log)', fontsize=12)
        plt.ylabel('Valor Keras (Log)', fontsize=12)
        plt.title('Keras vs ASPEN (Log-Log)', fontsize=14, fontweight='bold')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_dir / '6_keras_vs_aspen_loglog.png', dpi=150, bbox_inches='tight')
        plt.close()

    # 7. Top 10 variaveis maior erro medio
    if 'erro_abs' in df.columns:
        erro_var = df.groupby('variavel')['erro_abs'].mean().sort_values(ascending=False).head(10)
        plt.figure(figsize=(12, 8))
        erro_var.plot(kind='barh', color='coral')
        plt.xlabel('Erro Absoluto Medio', fontsize=12)
        plt.ylabel('Variavel', fontsize=12)
        plt.title('Top 10 Variaveis com Maior Erro Medio', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_dir / '7_top10_variaveis_erro.png', dpi=150, bbox_inches='tight')
        plt.close()

    print(f"Graficos salvos em {output_dir}")


def gerar_grafico_tira_teima(df, output_dir, n_variaveis=10):
    print(f"\nGerando graficos Tira-Teima para top {n_variaveis} variaveis...")

    variaveis_erro = []
    for variavel in df['variavel'].unique():
        df_var = df[df['variavel'] == variavel]
        k, a   = df_var['keras'].values, df_var['aspen'].values
        mask   = ~(np.isnan(k) | np.isnan(a))
        k, a   = k[mask], a[mask]
        if len(k) > 0:
            smape = np.mean(200 * np.abs(k - a) / (np.abs(a) + np.abs(k) + 1e-10))
            variaveis_erro.append({'variavel': variavel, 'smape': smape, 'n_pontos': len(k)})

    df_top   = pd.DataFrame(variaveis_erro).sort_values('smape', ascending=False).head(n_variaveis)
    tira_dir = output_dir / 'tira_teima'
    tira_dir.mkdir(exist_ok=True)

    for pos, (_, row) in enumerate(df_top.iterrows(), 1):
        variavel = row['variavel']
        df_var   = df[df['variavel'] == variavel].dropna(subset=['keras', 'aspen'])
        if len(df_var) == 0:
            continue

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

        ax1.scatter(df_var['aspen'], df_var['keras'], alpha=0.6, s=50,
                    edgecolors='black', linewidth=0.5)
        min_val = min(df_var['aspen'].min(), df_var['keras'].min())
        max_val = max(df_var['aspen'].max(), df_var['keras'].max())
        ax1.plot([min_val, max_val], [min_val, max_val], 'r--', lw=2, label='Perfeito (y=x)')
        x_band = np.array([min_val, max_val])
        ax1.fill_between(x_band, x_band * 0.9, x_band * 1.1,
                         alpha=0.2, color='green', label='+-10%')

        try:
            slope, intercept, r_value, _, _ = stats.linregress(df_var['aspen'], df_var['keras'])
            ax1.plot(x_band, slope * x_band + intercept, 'b-', lw=2, alpha=0.7,
                     label=f'Regressao (slope={slope:.3f})')
        except Exception:
            slope, r_value = 1.0, 1.0

        ax1.set_xlabel('Valor Real (ASPEN)', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Valor Previsto (Keras)', fontsize=12, fontweight='bold')
        ax1.set_title(f'{variavel}\nSMAPE: {row["smape"]:.2f}% | N={row["n_pontos"]}',
                      fontsize=12, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)

        df_var = df_var.copy()
        df_var['erro_pct_calc'] = ((df_var['keras'] - df_var['aspen']) /
                                   (df_var['aspen'].abs() + 1e-10)) * 100

        try:
            df_var['quartil'] = pd.qcut(df_var['aspen'], q=4,
                                        labels=['Q1 (Baixo)', 'Q2', 'Q3', 'Q4 (Alto)'],
                                        duplicates='drop')
            df_var.boxplot(column='erro_pct_calc', by='quartil', ax=ax2)
        except Exception:
            ax2.hist(df_var['erro_pct_calc'], bins=20, edgecolor='black', alpha=0.7)
            ax2.set_ylabel('Frequencia', fontsize=12)

        ax2.axhline(y=0,   color='red',    linestyle='--', lw=2)
        ax2.axhline(y=10,  color='orange', linestyle='--', lw=1, alpha=0.7)
        ax2.axhline(y=-10, color='orange', linestyle='--', lw=1, alpha=0.7)
        ax2.set_xlabel('Quartil', fontsize=12)
        ax2.set_ylabel('Erro %', fontsize=12)
        ax2.set_title('Erro por Faixa de Valor', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        plt.suptitle('')

        # Diagnostico automatico
        diagnostico = []
        erro_medio = df_var['erro_pct_calc'].mean()
        if erro_medio > 5:
            diagnostico.append(f"VIES: Superestima em media +{erro_medio:.1f}%")
        elif erro_medio < -5:
            diagnostico.append(f"VIES: Subestima em media {erro_medio:.1f}%")
        if slope < 0.95:
            diagnostico.append(f"SATURACAO: Slope={slope:.3f} < 0.95")
        elif slope > 1.05:
            diagnostico.append(f"AMPLIFICACAO: Slope={slope:.3f} > 1.05")
        if r_value**2 < 0.8:
            diagnostico.append(f"DISPERSAO ALTA: R2={r_value**2:.3f} < 0.8")

        texto_diag = '\n'.join(diagnostico) if diagnostico else 'Desempenho adequado'
        fig.text(0.5, 0.02, f"DIAGNOSTICO:\n{texto_diag}",
                 ha='center', fontsize=11,
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        plt.tight_layout(rect=[0, 0.08, 1, 1])
        nome = f"{pos:02d}_{variavel.replace('/', '_').replace(' ', '_')}.png"
        plt.savefig(tira_dir / nome, dpi=150, bbox_inches='tight')
        plt.close()

    print(f"{len(df_top)} graficos Tira-Teima salvos em {tira_dir}")


def gerar_heatmap_smape(df, coluna_grupo, output_dir, limiar_smape=15):
    print(f"\nGerando Heatmap SMAPE > {limiar_smape}%...")

    pivot_data = []
    for (grupo, var), g in df.groupby([coluna_grupo, 'variavel']):
        k, a  = g['keras'].values, g['aspen'].values
        mask  = ~(np.isnan(k) | np.isnan(a))
        k, a  = k[mask], a[mask]
        if len(k) > 0:
            smape = np.mean(200 * np.abs(k - a) / (np.abs(a) + np.abs(k) + 1e-10))
            pivot_data.append({'Variavel': var, 'Grupo': str(grupo), 'SMAPE': smape})

    if not pivot_data:
        print("Sem dados para heatmap.")
        return

    df_pivot  = pd.DataFrame(pivot_data)
    vars_prob = df_pivot[df_pivot['SMAPE'] > limiar_smape]['Variavel'].unique()
    df_filt   = df_pivot[df_pivot['Variavel'].isin(vars_prob)]

    if df_filt.empty:
        print(f"Nenhuma variavel com SMAPE > {limiar_smape}%.")
        return

    top_vars  = df_filt.groupby('Variavel')['SMAPE'].max().sort_values(ascending=False).head(25).index
    df_top    = df_filt[df_filt['Variavel'].isin(top_vars)]
    pivot_tbl = df_top.pivot(index='Variavel', columns='Grupo', values='SMAPE')
    pivot_msk = pivot_tbl.copy()
    pivot_msk[pivot_msk < limiar_smape] = np.nan

    fig, ax = plt.subplots(figsize=(16, 12))
    sns.heatmap(pivot_msk, annot=True, fmt='.1f', cmap='YlOrRd',
                vmin=limiar_smape, vmax=50,
                cbar_kws={'label': 'SMAPE (%)'},
                linewidths=0.5, linecolor='gray',
                ax=ax, mask=pivot_msk.isna())
    ax.set_title(f'Zonas de RISCO (SMAPE > {limiar_smape}%) - Top 25 Variaveis\n'
                 'Celulas em branco = Modelo OK',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_dir / f'heatmap_zona_confianca_limiar{limiar_smape}.png',
                dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Heatmap salvo em {output_dir}")

# ==============================================================================
# RELATORIO
# ==============================================================================

def gerar_relatorio_resumo(df, df_grupos, df_var_grupo, df_recorrencia, output_dir):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    relatorio = f"""
{'='*80}
RELATORIO DE ANALISE - DIGITAL TWIN
{'='*80}
Data/Hora:          {timestamp}
Total de registros: {len(df):,}
Total de casos:     {df['caso_id'].nunique()}
Total de variaveis: {df['variavel'].nunique()}

{'='*80}
ESTATISTICAS GERAIS
{'='*80}
"""
    if 'erro_abs' in df.columns:
        relatorio += f"Erro Absoluto Medio:  {df['erro_abs'].mean():.6f}\n"
        relatorio += f"Erro Absoluto Maximo: {df['erro_abs'].max():.6f}\n"
    if 'erro_pct' in df.columns:
        relatorio += f"Erro Percentual Medio: {df['erro_pct'].mean():.2f}%\n"

    relatorio += f"\n{'='*80}\nRESUMO POR GRUPO\n{'='*80}\n"
    for _, row in df_grupos.iterrows():
        relatorio += f"\n{row['Grupo']}\n{'─'*40}\n"
        relatorio += f"  N Casos:  {row['N_Casos']}\n"
        relatorio += f"  N Pontos: {row['N_Pontos']:,}\n"
        relatorio += f"  RMSE:     {row['RMSE']:.6f}\n"
        relatorio += f"  MAE:      {row['MAE']:.6f}\n"
        relatorio += f"  SMAPE:    {row['SMAPE']:.2f}%\n"
        relatorio += f"  R2:       {row['R2']:.4f}\n"
        if row['R2'] > 0.999:
            relatorio += "  AVISO: R2 > 0.999 - use SMAPE!\n"

    if not df_recorrencia.empty:
        relatorio += f"\n{'='*80}\nVARIAVEIS MAIS FREQUENTES NO TOP 10 PIORES\n{'='*80}\n"
        for _, row in df_recorrencia.head(10).iterrows():
            relatorio += f"\n{row['Variavel']}\n"
            relatorio += f"  Frequencia: {row['Frequencia_Top10']}\n"
            if 'erro_abs' in row:
                relatorio += f"  MAE medio:  {row['erro_abs']:.4f}\n"

    with open(output_dir / 'relatorio_resumo.txt', 'w', encoding='utf-8') as f:
        f.write(relatorio)

    print(relatorio)

# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("\n" + "="*60)
    print("ANALISE DE DIGITAL TWIN - KERAS vs ASPEN")
    print("="*60)

    csv_files = listar_csvs_disponiveis()
    if not csv_files:
        return

    arquivos_selecionados = selecionar_arquivos(csv_files)
    if not arquivos_selecionados:
        print("Nenhum arquivo selecionado.")
        return

    print(f"\n{len(arquivos_selecionados)} arquivo(s) selecionado(s)")

    dfs = []
    for arquivo in arquivos_selecionados:
        print(f"   Carregando: {arquivo.name}")
        try:
            dfs.append(pd.read_csv(arquivo))
        except Exception as e:
            print(f"Erro ao carregar {arquivo.name}: {e}")

    if not dfs:
        print("Nenhum arquivo carregado.")
        return

    df = pd.concat(dfs, ignore_index=True)
    print(f"Total: {len(df):,} registros")

    try:
        validar_dados(df)
    except ValueError as e:
        print(f"Erro na validacao: {e}")
        return

    # Detectar coluna de agrupamento
    df['porcentagem'] = df['descricao'].apply(extrair_porcentagem)
    tem_pct = df['porcentagem'].notna().sum() > 0

    if tem_pct:
        coluna_grupo = 'porcentagem'
        label_grupo  = 'porcentagem'
        print("\nAgrupando por porcentagem de variacao.")
    else:
        coluna_grupo = 'descricao'
        label_grupo  = 'descricao'
        print("\nFormato de porcentagem nao detectado — agrupando por descricao.")

    # Pasta de saida com timestamp
    timestamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_subdir = OUTPUT_DIR / f"analise_{timestamp}"
    output_subdir.mkdir(exist_ok=True)

    # Analises
    df_grupos    = analisar_por_grupo(df, coluna_grupo, label_grupo)
    df_casos     = analisar_por_caso(df)
    df_var_grupo = analisar_variaveis_por_grupo(df, coluna_grupo)
    df_melhores, df_piores = top_outputs_por_grupo(df, coluna_grupo, n=10)

    # Salvar CSVs
    print("\nSalvando resultados...")
    df_grupos.to_csv(output_subdir    / 'analise_por_grupo.csv',   index=False, encoding='utf-8-sig')
    df_casos.to_csv(output_subdir     / 'analise_por_caso.csv',    index=False, encoding='utf-8-sig')
    df_var_grupo.to_csv(output_subdir / 'analise_variaveis.csv',   index=False, encoding='utf-8-sig')
    if not df_melhores.empty:
        df_melhores.to_csv(output_subdir / 'top10_melhores.csv',   index=False, encoding='utf-8-sig')
    if not df_piores.empty:
        df_piores.to_csv(output_subdir   / 'top10_piores.csv',     index=False, encoding='utf-8-sig')

    diagnosticar_grandes_erros(df)
    df_recorrencia = analisar_recorrencia_top10(df_piores, df, output_subdir)

    gerar_graficos(df, df_grupos, coluna_grupo, output_subdir)
    gerar_grafico_tira_teima(df, output_subdir, n_variaveis=15)
    gerar_heatmap_smape(df, coluna_grupo, output_subdir, limiar_smape=15)
    gerar_relatorio_resumo(df, df_grupos, df_var_grupo, df_recorrencia, output_subdir)

    print(f"\n{'='*60}")
    print(f"ANALISE CONCLUIDA!")
    print(f"Resultados salvos em: {output_subdir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()