import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
import base64
from cryptography.fernet import Fernet
import unicodedata
import re

# --- Configurações gerais ---

PASTA_APP = os.path.dirname(__file__)  # Caminho relativo do arquivo para facilitar o deploy
ARQUIVO_ENCRIPTADO_PRODUCAO = os.path.join(PASTA_APP, "Informativo_Operacional.encrypted")
ARQUIVO_TEMP_PRODUCAO = os.path.join(PASTA_APP, "temp_Informativo_Operacional.xlsx")

ARQUIVO_ENCRIPTADO_QUALIDADE = os.path.join(PASTA_APP, "Relatorio_Qualidade.encrypted")
ARQUIVO_TEMP_QUALIDADE = os.path.join(PASTA_APP, "temp_Relatorio_Qualidade.xlsx")

CHAVE_HEX = os.getenv("HEX_KEY_STRING")
if not CHAVE_HEX:
    st.error("Chave de criptografia não foi encontrada nas variáveis de ambiente. " \
             "Por favor, configure a variável HEX_KEY_STRING no Secrets do Streamlit Cloud.")
    st.stop()

# Chave Fernet para criptografia/descriptografia
try:
    key_bytes = bytes.fromhex(CHAVE_HEX)
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    fernet = Fernet(fernet_key)
except Exception as e:
    st.error(f"Erro ao configurar chave de criptografia: {e}")
    st.stop()

# --- Funções de descriptografia ---

def descriptografar_arquivo(caminho_encriptado, caminho_saida):
    try:
        with open(caminho_encriptado, "rb") as f_enc:
            dados_enc = f_enc.read()
        dados_dec = fernet.decrypt(dados_enc)
        with open(caminho_saida, "wb") as f_out:
            f_out.write(dados_dec)
        return caminho_saida
    except Exception as e:
        st.error(f"Erro ao descriptografar o arquivo {os.path.basename(caminho_encriptado)}: {e}")
        return None

# --- Formatação brasileira ---

def format_number_br_no_decimals(number):
    if pd.isna(number) or number == 0:
        return "0"
    formatted = f"{number:,.0f}"
    formatted = formatted.replace(',', '.')
    return formatted

def format_number_br_with_decimals(number, decimals=2):
    if pd.isna(number) or number == 0:
        return "0"
    formatted = f"{number:,.{decimals}f}"
    formatted = formatted.replace(',', '|').replace('.', ',').replace('|', '.')
    return formatted

def format_percentage(value):
    return format_number_br_with_decimals(value, 2) + "%"

def format_measurement(value, unit="mm"):
    formatted = format_number_br_with_decimals(value, 2)
    return f"{formatted} {unit}" if formatted != "0" else "0"

# --- Funções para produção ---

MAPEAMENTO_COLUNAS_PRODUCAO = {
    '2025_Data': 'data',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 01_Lump': 'pm01_lump',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 01_Hemat': 'pm01_hematita',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 01_Sinter Feed\nNP': 'pm01_sinter',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 04_Lump': 'pm04_lump',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 04_Hemat': 'pm04_hematita',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 04_Sinter Feed\nNP': 'pm04_sinter',
}

META_DIARIA_PM = 5000
META_DIARIA_LUMP_PM = 3240
META_DIARIA_SINTER_PM = META_DIARIA_PM - META_DIARIA_LUMP_PM
META_DIARIA_TOTAL_COMBINADA = META_DIARIA_PM * 2
META_DIARIA_LUMP_COMBINADA = META_DIARIA_LUMP_PM * 2
META_DIARIA_SINTER_COMBINADA = META_DIARIA_SINTER_PM * 2

ESTOQUE_INICIAL = 189544
DATA_ESTOQUE_INICIAL = datetime(2025, 9, 16).date()

def carregar_e_tratar_dados_producao(caminho_excel):
    if caminho_excel is None or not os.path.exists(caminho_excel):
        st.error("Arquivo de produção não encontrado ou erro ao descriptografar.")
        return None
    try:
        df = pd.read_excel(caminho_excel, sheet_name="BD_Real", header=[0,1,2])

        # Remodelar nomes das colunas
        novas_colunas = ['_'.join([str(c) for c in col if 'Unnamed' not in str(c)]).strip() for col in df.columns]
        df.columns = novas_colunas

        df.rename(columns={k:v for k,v in MAPEAMENTO_COLUNAS_PRODUCAO.items() if k in df.columns}, inplace=True)

        colunas_necessarias = list(MAPEAMENTO_COLUNAS_PRODUCAO.values())
        colunas_presente = [col for col in colunas_necessarias if col in df.columns]

        if 'data' not in colunas_presente:
            st.error("Coluna 'data' não encontrada na planilha de produção.")
            return None

        df = df[colunas_presente]

        df.dropna(subset=['data'], inplace=True)
        df['data'] = pd.to_datetime(df['data'], errors='coerce')
        df.dropna(subset=['data'], inplace=True)

        # Converter colunas de produção para numérico
        for c in df.columns:
            if c != 'data':
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        # Soma total diária
        df['total_dia'] = df['pm01_lump'] + df['pm01_hematita'] + df['pm01_sinter'] + df['pm04_lump'] + df['pm04_hematita'] + df['pm04_sinter']

        return df
    
    except Exception as e:
        st.error(f"Erro ao processar planilha de produção: {e}")
        return None

# --- Funções para qualidade ---

NOME_ABA_QUALIDADE = "RESUMO GR"

def normalize_text(x: str) -> str:
    x = str(x).strip()
    x = ''.join(c for c in unicodedata.normalize('NFD', x) if unicodedata.category(c) != 'Mn')
    x = x.replace('%','').replace('(','').replace(')','').replace('\n',' ').replace('\r',' ').replace(',','.')
    x = x.lower()
    x = re.sub(r'\s+', ' ', x)
    return x

def map_column_name(col_name: str) -> str:
    s = normalize_text(col_name)
    mappings = {
        r'\bfe\b': 'Fe',
        r'sio2|si o2|silica|silicio|si02': 'SiO2',
        r'al2o3|alumina|al2': 'Al2O3',
        r'\bp\b': 'P',
        r'\bmn\b': 'Mn',
        r'ton': 'Ton',
        r'loi': 'LOI',
        r'\bmm\b|tamanho medio': 'TMP',
        r'(\+|>) *31(\.|,)5': '>31_5mm',
        r'- *12(?!.*umidade)': '_coluna_soma_1',
        r'- *6(\.|,)3': '_coluna_soma_2',
        r'total': 'TOTAL',
        r'data': 'Data'
    }
    for pattern, replacement in mappings.items():
        if re.search(pattern, s):
            return replacement
    if re.match(r'^\d+(\.|\d+)?$', s):
        return col_name.strip()
    return col_name.strip()

def flatten_multiindex_columns(df_block: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df_block.columns, pd.MultiIndex):
        return df_block
    new_cols = []
    for col in df_block.columns:
        if isinstance(col, tuple):
            a,b = col
            a_txt = '' if pd.isna(a) else str(a).strip()
            b_txt = '' if pd.isna(b) else str(b).strip()
            chosen = b_txt if b_txt else a_txt
            new_cols.append(chosen if chosen else f'{a}_{b}')
        else:
            new_cols.append(str(col))
    df_block.columns = new_cols
    return df_block

def carregar_e_tratar_dados_qualidade(caminho_excel):
    if caminho_excel is None or not os.path.exists(caminho_excel):
        st.error("Arquivo de qualidade não encontrado ou erro ao descriptografar.")
        return None
    try:
        df_raw = pd.read_excel(caminho_excel, sheet_name=NOME_ABA_QUALIDADE, header=[0,1], nrows=34, engine='openpyxl')

        # Achatar colunas MultiIndex
        df_raw = flatten_multiindex_columns(df_raw)
        df_raw.rename(columns={c: map_column_name(c) for c in df_raw.columns}, inplace=True)

        df_raw['Data'] = pd.to_datetime(df_raw['Data'], errors='coerce')

        # Conversão numérica para colunas numéricas, exceto Data
        for c in df_raw.columns:
            if c != 'Data':
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0)

        return df_raw

    except Exception as e:
        st.error(f"Erro ao processar planilha de qualidade: {e}")
        return None

# --- Dashboard Produção ---

def dashboard_producao():
    st.title("Dashboard de Produção - Peneiras Móveis Tuypacery")
    st.markdown("---")

    caminho_excel = descriptografar_arquivo(ARQUIVO_ENCRIPTADO_PRODUCAO, ARQUIVO_TEMP_PRODUCAO)
    df = carregar_e_tratar_dados_producao(caminho_excel)

    if df is None:
        return

    data_inicio_operacao = datetime(2025, 8, 26).date()
    data_fim_dados = df['data'].max().date()

    data_selecionada = st.sidebar.date_input(
        "Selecione o Período",
        value=(data_inicio_operacao, data_fim_dados),
        min_value=data_inicio_operacao,
        max_value=data_fim_dados,
        format="DD/MM/YYYY"
    )

    if len(data_selecionada) == 2:
        data_inicio_filtro, data_fim_filtro = data_selecionada
        df_filtrado = df[(df['data'].dt.date >= data_inicio_filtro) & (df['data'].dt.date <= data_fim_filtro)].copy()
    else:
        df_filtrado = df.copy()

    if df_filtrado.empty:
        st.warning("Não há dias produtivos para o período selecionado.")
        return

    # Cálculos similares aos seus atuais (totais diários, médias, KPIs)...

    df_filtrado['total_pm01'] = df_filtrado['pm01_lump'] + df_filtrado['pm01_hematita'] + df_filtrado['pm01_sinter']
    df_filtrado['total_pm04'] = df_filtrado['pm04_lump'] + df_filtrado['pm04_hematita'] + df_filtrado['pm04_sinter']
    df_filtrado['total_lump'] = df_filtrado['pm01_lump'] + df_filtrado['pm04_lump']
    df_filtrado['total_hematita'] = df_filtrado['pm01_hematita'] + df_filtrado['pm04_hematita']
    df_filtrado['total_sinter'] = df_filtrado['pm01_sinter'] + df_filtrado['pm04_sinter']
    df_filtrado['media_movel_7d'] = df_filtrado['total_dia'].rolling(window=7, min_periods=1).mean()

    df_produtivo = df_filtrado[df_filtrado['total_dia'] > 0].copy()
    dias_produtivos_combinado = len(df_produtivo)

    if dias_produtivos_combinado > 0:
        dias_produtivos_pm01 = (df_produtivo['total_pm01'] > 0).sum()
        dias_produtivos_pm04 = (df_produtivo['total_pm04'] > 0).sum()

        prod_total_pm01 = df_produtivo['total_pm01'].sum()
        prod_total_pm04 = df_produtivo['total_pm04'].sum()
        prod_total_combinada = df_produtivo['total_dia'].sum()

        media_pm01 = prod_total_pm01 / dias_produtivos_pm01 if dias_produtivos_pm01 > 0 else 0
        media_pm04 = prod_total_pm04 / dias_produtivos_pm04 if dias_produtivos_pm04 > 0 else 0
        media_combinada = prod_total_combinada / dias_produtivos_combinado if dias_produtivos_combinado > 0 else 0

        ultimo_dia_df = df_produtivo[df_produtivo['data'].dt.date == df_produtivo['data'].max().date()]
        prod_ultimo_dia_pm01 = ultimo_dia_df['total_pm01'].sum()
        prod_ultimo_dia_pm04 = ultimo_dia_df['total_pm04'].sum()
        prod_ultimo_dia_combinada = ultimo_dia_df['total_dia'].sum()

        meta_total_pm01_periodo = META_DIARIA_PM * dias_produtivos_pm01
        meta_total_pm04_periodo = META_DIARIA_PM * dias_produtivos_pm04
        meta_total_combinada_periodo = META_DIARIA_TOTAL_COMBINADA * dias_produtivos_combinado

        atingimento_pm01 = (prod_total_pm01 / meta_total_pm01_periodo) * 100 if meta_total_pm01_periodo > 0 else 0
        atingimento_pm04 = (prod_total_pm04 / meta_total_pm04_periodo) * 100 if meta_total_pm04_periodo > 0 else 0
        atingimento_combinado = (prod_total_combinada / meta_total_combinada_periodo) * 100 if meta_total_combinada_periodo > 0 else 0
    else:
        media_pm01 = media_pm04 = media_combinada = 0
        prod_ultimo_dia_pm01 = prod_ultimo_dia_pm04 = prod_ultimo_dia_combinada = 0
        atingimento_pm01 = atingimento_pm04 = atingimento_combinado = 0

    # Exemplo de KPIs
    st.subheader("Painel de Indicadores (KPIs)")
    st.markdown("##### Visão Geral (Combinado)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Produção Total no Período", f"{format_number_br_no_decimals(prod_total_combinada)} t")
    col2.metric("Média Diária (dias produtivos)", f"{format_number_br_no_decimals(media_combinada)} t")
    col3.metric(f"Produção do Último Dia ({df_produtivo['data'].max().strftime('%d/%m') if dias_produtivos_combinado > 0 else 'N/A'})",
                f"{format_number_br_no_decimals(prod_ultimo_dia_combinada)} t")
    col4.metric("Atingimento Meta Combinada", f"{atingimento_combinado:.1f}%".replace('.', ','))

    # Continua com seus gráficos e visualizações...

# --- Dashboard Qualidade ---

def dashboard_qualidade():
    st.title("Dashboard de Qualidade - LOHG")
    st.markdown("---")

    caminho_excel = descriptografar_arquivo(ARQUIVO_ENCRIPTADO_QUALIDADE, ARQUIVO_TEMP_QUALIDADE)
    df_qualidade = carregar_e_tratar_dados_qualidade(caminho_excel)

    if df_qualidade is None or df_qualidade.empty:
        st.warning("Nenhum dado disponível para qualidade.")
        return
    
    # Exemplo simples de exibição
    st.dataframe(df_qualidade.head())
    # Você deve completar com seus gráficos, KPIs e análises da qualidade


# --- APP principal com múltiplas páginas ---

st.set_page_config(layout="wide", page_title="Dashboard LOHG")

st.sidebar.title("Navegação")
pagina = st.sidebar.radio("Escolha a página", options=["Produção", "Qualidade"])

if pagina == "Produção":
    dashboard_producao()
elif pagina == "Qualidade":
    dashboard_qualidade()
