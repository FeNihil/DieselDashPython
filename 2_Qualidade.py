"""
Dashboard de Qualidade - Adaptado para ambiente Streamlit Cloud
Baseado na estrutura do 1_Producao.py para consistência
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from PIL import Image
import os
import io
import base64
from cryptography.fernet import Fernet
import zipfile
import re
import unicodedata

def is_valid_xlsx_bytes(b: bytes) -> bool:
    """
    Retorna True se os bytes representarem um arquivo ZIP válido,
    condição necessária para que seja um XLSX válido.
    """
    try:
        with io.BytesIO(b) as bio:
            return zipfile.is_zipfile(bio)
    except Exception:
        return False

# =========================
# Configuração de página
# =========================
st.set_page_config(layout="wide", page_title="Dashboard de Qualidade Tupacery")

st.markdown(
    "",
    unsafe_allow_html=True,
)

# =========================
# Chave e Fernet via secrets
# =========================
HEX_KEY_STRING = st.secrets.get("HEX_KEY_STRING", None)
fernet = None

if HEX_KEY_STRING:
    try:
        key_bytes = bytes.fromhex(HEX_KEY_STRING)
        ENCRYPTION_KEY = base64.urlsafe_b64encode(key_bytes)
        fernet = Fernet(ENCRYPTION_KEY)
    except ValueError as e:
        st.error(f"❌ Erro na chave de criptografia. Verifique HEX_KEY_STRING no secrets: {e}")
else:
    st.error("❌ HEX_KEY_STRING ausente em st.secrets. Configure em Secrets do Streamlit Cloud.")

# =========================
# Constantes e caminhos
# =========================
NOME_ARQUIVO_QUALIDADE_SALVO = "Relatorio_Qualidade.encrypted"  # arquivo criptografado
CAMINHO_LOGO = "Lhg-02.png"
NOME_ABA_QUALIDADE = "RESUMO GR"

# =========================
# Funções de formatação brasileira
# =========================
def format_brazilian_number(value, decimals=2):
    """Formatar número no padrão brasileiro (1.234,22)"""
    if pd.isna(value) or value is None:
        return "N/D"
    try:
        num_value = float(value)
        if decimals == 0:
            return f"{num_value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            return f"{num_value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "N/D"

def format_percentage(value):
    """Formatar porcentagem no padrão brasileiro"""
    return format_brazilian_number(value, 2) + "%"

def format_measurement(value, unit="mm"):
    """Formatar medidas com unidade"""
    formatted = format_brazilian_number(value, 2)
    return f"{formatted} {unit}" if formatted != "N/D" else "N/D"

# =========================
# Funções de normalização de texto
# =========================
def normalize_text(x: str) -> str:
    """Normalizar texto removendo acentos e caracteres especiais"""
    x = str(x).strip()
    x = ''.join(c for c in unicodedata.normalize('NFD', x) if unicodedata.category(c) != 'Mn')
    x = x.replace('%', '').replace('(', '').replace(')', '')
    x = x.replace('\n', ' ').replace('\r', ' ').replace(',', '.').lower()
    x = re.sub(r'\s+', ' ', x)
    return x

def map_column_name(col_name: str) -> str:
    """Mapear nome de coluna para padrão conhecido"""
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

# =========================
# I/O: carregar bytes criptografados e descriptografar
# =========================
def ler_bytes_arquivo_local(caminho: str) -> bytes | None:
    """
    Lê arquivo local sem cache - sempre pega a versão mais atual do repositório
    """
    if not os.path.exists(caminho):
        return None
    try:
        # Obtém informações do arquivo para verificar se mudou
        stat_info = os.stat(caminho)
        file_size = stat_info.st_size
        file_mtime = stat_info.st_mtime

        # Cria uma chave única baseada no arquivo
        cache_key = f"{caminho}_{file_size}_{file_mtime}"

        # Verifica se já temos este arquivo em cache
        if 'file_cache_qualidade' not in st.session_state:
            st.session_state['file_cache_qualidade'] = {}

        if cache_key in st.session_state['file_cache_qualidade']:
            return st.session_state['file_cache_qualidade'][cache_key]

        # Lê o arquivo
        with open(caminho, "rb") as f:
            file_bytes = f.read()

        # Limpa cache antigo e salva o novo
        st.session_state['file_cache_qualidade'] = {cache_key: file_bytes}

        return file_bytes
    except Exception as e:
        st.error(f"Erro ao ler arquivo {caminho}: {e}")
        return None

def descriptografar_bytes(cipher_bytes: bytes, fernet_obj: Fernet) -> bytes | None:
    try:
        return fernet_obj.decrypt(cipher_bytes)
    except Exception as e:
        st.error(f"Erro ao descriptografar o arquivo: {e}")
        return None

# =========================
# Processamento de dados específico para qualidade
# =========================
def flatten_multiindex_columns(df_block: pd.DataFrame) -> pd.DataFrame:
    """Achatar colunas multi-índice"""
    if not isinstance(df_block.columns, pd.MultiIndex):
        return df_block

    new_cols = []
    for col in df_block.columns:
        if isinstance(col, tuple):
            a, b = col
            a_txt = '' if pd.isna(a) else str(a).strip()
            b_txt = '' if pd.isna(b) else str(b).strip()
            chosen = b_txt if b_txt else a_txt
            new_cols.append(chosen if chosen else f"{a}_{b}")
        else:
            new_cols.append(str(col))

    df_block.columns = new_cols
    return df_block

def detect_data_blocks(df_raw: pd.DataFrame):
    """Detectar blocos de dados (PMT 01 e PMT 02)"""
    try:
        lvl1 = df_raw.columns.get_level_values(1).tolist()
        lvl1_norm = [normalize_text(x) if not pd.isna(x) else '' for x in lvl1]

        start_idxs = [i for i, v in enumerate(lvl1_norm) if 'data' in v]

        if len(start_idxs) >= 2:
            blocks = []
            for i, s in enumerate(start_idxs):
                e = start_idxs[i + 1] - 1 if i + 1 < len(start_idxs) else (df_raw.shape[1] - 1)
                blocks.append((s, e))
            return blocks[:2]
    except Exception:
        pass

    # Fallback para índices conhecidos
    return [(260, 267), (709, 716)]

def process_dataframe_block(df_block: pd.DataFrame) -> pd.DataFrame:
    """Processar um bloco de dados"""
    df_block = flatten_multiindex_columns(df_block)

    df_block.rename(columns={c: map_column_name(c) for c in df_block.columns}, inplace=True)

    # Remover duplicatas de colunas
    cols = list(df_block.columns)
    seen = {}
    new_cols = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 1
            new_cols.append(c)
    df_block.columns = new_cols

    # Encontrar e renomear coluna de data
    date_col = None
    for c in df_block.columns:
        if 'data' in normalize_text(c):
            date_col = c
            break

    if date_col:
        df_block.rename(columns={date_col: 'Data'}, inplace=True)
    else:
        df_block.rename(columns={df_block.columns[0]: 'Data'}, inplace=True)

    # Converter tipos de dados
    df_block['Data'] = pd.to_datetime(df_block['Data'], errors='coerce')
    for col in df_block.columns:
        if col != 'Data':
            df_block[col] = pd.to_numeric(df_block[col], errors='coerce')

    # Calcular coluna <0_15mm se necessário
    if '_coluna_soma_1' in df_block.columns and '_coluna_soma_2' in df_block.columns:
        df_block['<0_15mm'] = df_block['_coluna_soma_1'].fillna(0) + df_block['_coluna_soma_2'].fillna(0)

    return df_block

@st.cache_data(ttl=300)  # Cache reduzido para 5 minutos
def carregar_excel_qualidade_em_df(excel_bytes: bytes) -> tuple:
    """Carregar e processar dados de qualidade"""
    try:
        df_raw = pd.read_excel(
            io.BytesIO(excel_bytes), 
            sheet_name=NOME_ABA_QUALIDADE, 
            header=[0, 1], 
            nrows=34,
            engine='openpyxl'
        )

        # Detectar blocos de dados
        blocks = detect_data_blocks(df_raw)

        # Processar blocos PMT 01 e PMT 02
        s1, e1 = blocks[0]
        s2, e2 = blocks[1]

        df_pmt01 = process_dataframe_block(df_raw.iloc[:, s1:e1+1].copy())
        df_pmt02 = process_dataframe_block(df_raw.iloc[:, s2:e2+1].copy())

        # Encontrar última data válida
        def find_last_valid_date(df_block):
            if 'Ton' in df_block.columns:
                mask = pd.to_numeric(df_block['Ton'], errors='coerce').fillna(0) > 0
                if mask.any():
                    return df_block.loc[mask, 'Data'].max()

            numeric_cols = [c for c in df_block.columns if c != 'Data']
            if numeric_cols:
                mask = df_block[numeric_cols].notna().any(axis=1)
                if mask.any():
                    return df_block.loc[mask, 'Data'].max()

            return df_block['Data'].dropna().max() if df_block['Data'].notna().any() else pd.NaT

        last1 = find_last_valid_date(df_pmt01)
        last2 = find_last_valid_date(df_pmt02)

        valid_dates = [d for d in [last1, last2] if not pd.isna(d)]
        if not valid_dates:
            st.error("Nenhuma data válida encontrada nos dados.")
            return None, None, None, None

        ultimo_dia = max(valid_dates)

        # Preparar dados do último dia
        indicadores_padrao = ['Fe', 'SiO2', 'Al2O3', 'TMP', '>31_5mm', '<0_15mm']

        def get_data_for_date(df_block, target_date):
            try:
                mask = df_block['Data'] == target_date
                if mask.any():
                    return df_block.loc[mask].iloc[0].drop(labels='Data')
            except Exception:
                pass

            if 'Ton' in df_block.columns:
                try:
                    mask = pd.to_numeric(df_block['Ton'], errors='coerce').fillna(0) > 0
                    if mask.any():
                        return df_block.loc[mask].iloc[-1].drop(labels='Data')
                except Exception:
                    pass

            numeric_cols = [c for c in df_block.columns if c != 'Data']
            mask = df_block[numeric_cols].notna().any(axis=1)
            if mask.any():
                return df_block.loc[mask].iloc[-1].drop(labels='Data')

            return pd.Series([pd.NA] * len(numeric_cols), index=numeric_cols)

        row_pmt01 = get_data_for_date(df_pmt01, ultimo_dia)
        row_pmt02 = get_data_for_date(df_pmt02, ultimo_dia)

        # Criar DataFrame do dia
        dia_data = {}
        for indicador in indicadores_padrao:
            dia_data[indicador] = [
                row_pmt01.get(indicador, pd.NA),
                row_pmt02.get(indicador, pd.NA)
            ]

        dia = pd.DataFrame(dia_data, index=['PMT 01', 'PMT 02']).T
        dia.loc['PRODUTO_DIA'] = [ultimo_dia, ultimo_dia]

        # Calcular médias mensais
        def calc_monthly_mean(df_block):
            if 'Ton' in df_block.columns:
                productive_mask = pd.to_numeric(df_block['Ton'], errors='coerce').fillna(0) > 0
                subset = df_block[productive_mask] if productive_mask.any() else df_block
            else:
                numeric_cols = [c for c in df_block.columns if c != 'Data']
                subset = df_block[df_block[numeric_cols].notna().any(axis=1)]

            means = {}
            for indicador in indicadores_padrao:
                if indicador in subset.columns:
                    means[indicador] = subset[indicador].mean()
                else:
                    means[indicador] = pd.NA
            return pd.Series(means)

        media_pmt01 = calc_monthly_mean(df_pmt01)
        media_pmt02 = calc_monthly_mean(df_pmt02)
        media = pd.DataFrame({'PMT 01': media_pmt01, 'PMT 02': media_pmt02})

        # Preparar dados para boxplot
        df_pmt01_box = df_pmt01.copy()
        df_pmt01_box['Peneira'] = 'PMT 01'
        df_pmt02_box = df_pmt02.copy()
        df_pmt02_box['Peneira'] = 'PMT 02'

        boxplot_data = pd.concat([df_pmt01_box, df_pmt02_box], ignore_index=True)
        boxplot_data = boxplot_data[boxplot_data['Data'].notna()].reset_index(drop=True)

        # Formatar mês de referência
        mes_num = ultimo_dia.strftime('%m/%Y')
        meses_pt = {
            '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
            '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
            '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro'
        }
        mm = mes_num.split('/')[0]
        mes_pt = f"{meses_pt.get(mm, mm)}/{mes_num.split('/')[1]}"

        return dia, media, boxplot_data, mes_pt

    except Exception as e:
        st.error(f"Erro ao ler/processar a planilha de qualidade: {e}")
        return None, None, None, None

# =========================
# Header e logo
# =========================
try:
    if os.path.exists(CAMINHO_LOGO):
        logo = Image.open(CAMINHO_LOGO)
        st.image(logo, width=200)
    else:
        st.info("Logo não encontrada (Lhg-02.png). Coloque o arquivo na raiz do app.")
except Exception:
    st.info("Falha ao carregar a logo. Verifique o arquivo Lhg-02.png.")

st.title("Dashboard de Qualidade - Peneiras Móveis Tupacery")
st.markdown("---")

# =========================
# Entrada de dados: prioriza arquivo no repo; fallback uploader
# =========================
def carregar_dados_qualidade_automaticamente() -> tuple:
    """
    Carrega dados de qualidade automaticamente, priorizando arquivo do repositório
    """
    if fernet is None:
        st.error("Chave Fernet indisponível; verifique HEX_KEY_STRING em secrets.")
        return None, None, None, None

    # 1) Tentar ler o token criptografado do repositório
    cipher_bytes_repo = ler_bytes_arquivo_local(NOME_ARQUIVO_QUALIDADE_SALVO)
    if cipher_bytes_repo:
        st.success(f"✅ Dados de qualidade carregados do repositório: {NOME_ARQUIVO_QUALIDADE_SALVO}")
        plain_bytes = descriptografar_bytes(cipher_bytes_repo, fernet)
        if plain_bytes:
            resultado = carregar_excel_qualidade_em_df(plain_bytes)
            if resultado[0] is not None:
                # Mostra informação sobre a última atualização
                try:
                    stat_info = os.stat(NOME_ARQUIVO_QUALIDADE_SALVO)
                    ultima_modificacao = datetime.fromtimestamp(stat_info.st_mtime)
                    st.info(f"📅 Última atualização: {ultima_modificacao.strftime('%d/%m/%Y às %H:%M:%S')}")
                except:
                    pass
                return resultado
            else:
                st.warning("Descriptografia ocorreu, mas leitura do Excel de qualidade falhou.")

    # 2) Fallback: upload do arquivo criptografado
    st.warning("⚠️ Arquivo de qualidade não encontrado no repositório. Faça upload do arquivo criptografado:")
    up = st.file_uploader(
        "Selecione o arquivo Excel de qualidade criptografado (token Fernet)",
        type=["encrypted", "bin", "xlsx"],
        help="Envie o arquivo .encrypted gerado pelo processo de criptografia",
        key="qualidade_uploader"
    )

    if up is not None:
        st.write(f"📁 Arquivo recebido: {up.name}")
        up_bytes = up.read()
        st.write(f"📊 Tamanho do arquivo: {len(up_bytes)} bytes")

        # Tenta descriptografar primeiro (caminho padrão)
        plain_bytes = descriptografar_bytes(up_bytes, fernet)
        if plain_bytes:
            st.success("🔓 Descriptografia realizada com sucesso!")
            resultado = carregar_excel_qualidade_em_df(plain_bytes)
            if resultado[0] is not None:
                return resultado
            else:
                st.warning("Descriptografia OK, mas XLSX de qualidade inválido.")
        else:
            # Fallback opcional para testes: tentar ler como XLSX em claro
            st.warning("⚠️ Tentando interpretar como XLSX não criptografado (apenas para testes)...")
            if is_valid_xlsx_bytes(up_bytes):
                resultado = carregar_excel_qualidade_em_df(up_bytes)
                if resultado[0] is not None:
                    st.info("📈 Arquivo lido sem criptografia (modo de teste)")
                    return resultado
                else:
                    st.error("❌ Falha ao ler arquivo como XLSX de qualidade.")
            else:
                st.error("❌ Arquivo não é um token Fernet válido nem um XLSX válido.")

    return None, None, None, None

# Carregamento automático dos dados
df_qualidade_dia, df_qualidade_media, df_boxplot, mes_referencia = carregar_dados_qualidade_automaticamente()

if df_qualidade_dia is None:
    st.error("❌ Não foi possível carregar os dados de qualidade. Verifique o arquivo criptografado e a chave em secrets.")
    st.stop()

# =========================
# Sidebar de metas
# =========================
st.sidebar.header("🎯 Metas de Qualidade")
st.sidebar.markdown(f"**📅 Mês: {mes_referencia if mes_referencia else 'N/D'}**")
st.sidebar.markdown("---")

st.sidebar.subheader("🧪 Químicos (%)")
meta_fe_min = st.sidebar.number_input("Fe (Mínimo)", value=65.0, step=0.1)
meta_sio2_max = st.sidebar.number_input("SiO₂ (Máximo)", value=1.5, step=0.1)
meta_al2o3_max = st.sidebar.number_input("Al₂O₃ (Máximo)", value=0.8, step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("⚖️ Físicos")
meta_tmp = st.sidebar.number_input("TMP (mm)", value=18.0, step=0.5)
meta_acima_31mm_max = st.sidebar.number_input(">31,5mm (%)", value=10.0, step=1.0)
meta_abaixo_015mm_max = st.sidebar.number_input("<0,15mm (%)", value=5.0, step=1.0)

# Informação sobre atualização automática
st.sidebar.markdown("---")
st.sidebar.info("🔄 Os dados são atualizados automaticamente quando o arquivo for modificado no repositório.")

# =========================
# Dashboard principal
# =========================

# Extrair data do último dia
try:
    produto_dia_raw = df_qualidade_dia.loc['PRODUTO_DIA', 'PMT 01']
    produto_dia_str = pd.to_datetime(produto_dia_raw).strftime('%d/%m/%Y')
except Exception:
    produto_dia_str = 'N/D'

# === RESULTADOS DO ÚLTIMO DIA ===
st.subheader(f"📊 Resultados do Último Dia ({produto_dia_str})")

col1, col2 = st.columns(2)

# PMT 01
with col1:
    st.markdown("### 🏭 PMT 01 - TUPACERY")

    # Métricas químicas
    subcol1, subcol2, subcol3 = st.columns(3)
    with subcol1:
        fe_val = df_qualidade_dia.loc['Fe', 'PMT 01'] if 'Fe' in df_qualidade_dia.index else None
        st.metric("Fe", format_percentage(fe_val))
    with subcol2:
        sio2_val = df_qualidade_dia.loc['SiO2', 'PMT 01'] if 'SiO2' in df_qualidade_dia.index else None
        st.metric("SiO₂", format_percentage(sio2_val))
    with subcol3:
        al2o3_val = df_qualidade_dia.loc['Al2O3', 'PMT 01'] if 'Al2O3' in df_qualidade_dia.index else None
        st.metric("Al₂O₃", format_percentage(al2o3_val))

    # Métricas físicas
    subcol4, subcol5, subcol6 = st.columns(3)
    with subcol4:
        tmp_val = df_qualidade_dia.loc['TMP', 'PMT 01'] if 'TMP' in df_qualidade_dia.index else None
        st.metric("TMP", format_measurement(tmp_val, "mm"))
    with subcol5:
        acima31_val = df_qualidade_dia.loc['>31_5mm', 'PMT 01'] if '>31_5mm' in df_qualidade_dia.index else None
        st.metric(">31,5mm", format_percentage(acima31_val))
    with subcol6:
        abaixo015_val = df_qualidade_dia.loc['<0_15mm', 'PMT 01'] if '<0_15mm' in df_qualidade_dia.index else None
        st.metric("<0,15mm", format_percentage(abaixo015_val))

# PMT 02
with col2:
    st.markdown("### 🏭 PMT 02 - TUPACERY")

    # Métricas químicas
    subcol1, subcol2, subcol3 = st.columns(3)
    with subcol1:
        fe_val = df_qualidade_dia.loc['Fe', 'PMT 02'] if 'Fe' in df_qualidade_dia.index else None
        st.metric("Fe", format_percentage(fe_val))
    with subcol2:
        sio2_val = df_qualidade_dia.loc['SiO2', 'PMT 02'] if 'SiO2' in df_qualidade_dia.index else None
        st.metric("SiO₂", format_percentage(sio2_val))
    with subcol3:
        al2o3_val = df_qualidade_dia.loc['Al2O3', 'PMT 02'] if 'Al2O3' in df_qualidade_dia.index else None
        st.metric("Al₂O₃", format_percentage(al2o3_val))

    # Métricas físicas
    subcol4, subcol5, subcol6 = st.columns(3)
    with subcol4:
        tmp_val = df_qualidade_dia.loc['TMP', 'PMT 02'] if 'TMP' in df_qualidade_dia.index else None
        st.metric("TMP", format_measurement(tmp_val, "mm"))
    with subcol5:
        acima31_val = df_qualidade_dia.loc['>31_5mm', 'PMT 02'] if '>31_5mm' in df_qualidade_dia.index else None
        st.metric(">31,5mm", format_percentage(acima31_val))
    with subcol6:
        abaixo015_val = df_qualidade_dia.loc['<0_15mm', 'PMT 02'] if '<0_15mm' in df_qualidade_dia.index else None
        st.metric("<0,15mm", format_percentage(abaixo015_val))

st.markdown("---")

# === MÉDIA DO MÊS ===
st.subheader("📈 Média Geral do Mês")

col1, col2 = st.columns(2)

# PMT 01 - Média
with col1:
    st.markdown("### 🏭 PMT 01 - TUPACERY")

    subcol1, subcol2, subcol3 = st.columns(3)
    with subcol1:
        fe_media = df_qualidade_media.loc['Fe', 'PMT 01'] if 'Fe' in df_qualidade_media.index else None
        st.metric("Fe (Média)", format_percentage(fe_media))
    with subcol2:
        sio2_media = df_qualidade_media.loc['SiO2', 'PMT 01'] if 'SiO2' in df_qualidade_media.index else None
        st.metric("SiO₂ (Média)", format_percentage(sio2_media))
    with subcol3:
        al2o3_media = df_qualidade_media.loc['Al2O3', 'PMT 01'] if 'Al2O3' in df_qualidade_media.index else None
        st.metric("Al₂O₃ (Média)", format_percentage(al2o3_media))

    subcol4, subcol5, subcol6 = st.columns(3)
    with subcol4:
        tmp_media = df_qualidade_media.loc['TMP', 'PMT 01'] if 'TMP' in df_qualidade_media.index else None
        st.metric("TMP (Média)", format_measurement(tmp_media, "mm"))
    with subcol5:
        acima31_media = df_qualidade_media.loc['>31_5mm', 'PMT 01'] if '>31_5mm' in df_qualidade_media.index else None
        st.metric(">31,5mm (Média)", format_percentage(acima31_media))
    with subcol6:
        abaixo015_media = df_qualidade_media.loc['<0_15mm', 'PMT 01'] if '<0_15mm' in df_qualidade_media.index else None
        st.metric("<0,15mm (Média)", format_percentage(abaixo015_media))

# PMT 02 - Média
with col2:
    st.markdown("### 🏭 PMT 02 - TUPACERY")

    subcol1, subcol2, subcol3 = st.columns(3)
    with subcol1:
        fe_media = df_qualidade_media.loc['Fe', 'PMT 02'] if 'Fe' in df_qualidade_media.index else None
        st.metric("Fe (Média)", format_percentage(fe_media))
    with subcol2:
        sio2_media = df_qualidade_media.loc['SiO2', 'PMT 02'] if 'SiO2' in df_qualidade_media.index else None
        st.metric("SiO₂ (Média)", format_percentage(sio2_media))
    with subcol3:
        al2o3_media = df_qualidade_media.loc['Al2O3', 'PMT 02'] if 'Al2O3' in df_qualidade_media.index else None
        st.metric("Al₂O₃ (Média)", format_percentage(al2o3_media))

    subcol4, subcol5, subcol6 = st.columns(3)
    with subcol4:
        tmp_media = df_qualidade_media.loc['TMP', 'PMT 02'] if 'TMP' in df_qualidade_media.index else None
        st.metric("TMP (Média)", format_measurement(tmp_media, "mm"))
    with subcol5:
        acima31_media = df_qualidade_media.loc['>31_5mm', 'PMT 02'] if '>31_5mm' in df_qualidade_media.index else None
        st.metric(">31,5mm (Média)", format_percentage(acima31_media))
    with subcol6:
        abaixo015_media = df_qualidade_media.loc['<0_15mm', 'PMT 02'] if '<0_15mm' in df_qualidade_media.index else None
        st.metric("<0,15mm (Média)", format_percentage(abaixo015_media))

st.markdown("---")

# === ANÁLISE DE DISTRIBUIÇÃO ===
st.subheader("📊 Distribuição e Consistência da Qualidade no Mês")

if isinstance(df_boxplot, pd.DataFrame) and not df_boxplot.empty:
    indicadores_disponiveis = ['Fe', 'SiO2', 'Al2O3', 'TMP', '>31_5mm', '<0_15mm']

    indicador_selecionado = st.selectbox(
        "🎯 Selecione um Indicador para Análise Detalhada",
        options=indicadores_disponiveis
    )

    if indicador_selecionado:
        # Converter e filtrar: dropna e remover zeros
        df_boxplot[indicador_selecionado] = pd.to_numeric(df_boxplot[indicador_selecionado], errors='coerce')
        df_plot = df_boxplot.dropna(subset=[indicador_selecionado, 'Data']).copy()
        df_plot = df_plot[df_plot[indicador_selecionado] != 0]  # ignora zeros

        if not df_plot.empty:
            fig_boxplot = px.box(
                df_plot,
                x='Peneira',
                y=indicador_selecionado,
                color='Peneira',
                points=False,  # opcional: oculta pontos/outliers
                title=f"📊 Distribuição de {indicador_selecionado} por Peneira - {st.session_state['mes_referencia']}"
            )
            fig_boxplot.update_layout(
                template='plotly_white',
                font=dict(size=12),
                title_font=dict(size=16),
                showlegend=True,
                height=500,
                yaxis=dict(zeroline=False)  # opcional: remove linha em 0
            )
            fig_boxplot.update_yaxes(
                tickformat=',.2f',
                title=f"{indicador_selecionado} ({'%' if indicador_selecionado in ['Fe', 'SiO2', 'Al2O3', '>31_5mm', '<0_15mm'] else 'mm' if indicador_selecionado == 'TMP' else ''})"
            )
            st.plotly_chart(fig_boxplot, use_container_width=True)

            # Estatísticas descritivas (já sem zeros)
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 📈 Estatísticas - PMT 01")
                pmt01_data_filtered = df_plot.loc[df_plot['Peneira']=='PMT 01', indicador_selecionado]
                if not pmt01_data_filtered.empty:
                    st.write(f"**Média:** {format_brazilian_number(pmt01_data_filtered.mean())}")
                    st.write(f"**Mediana:** {format_brazilian_number(pmt01_data_filtered.median())}")
                    st.write(f"**Desvio Padrão:** {format_brazilian_number(pmt01_data_filtered.std())}")
                    st.write(f"**Mínimo:** {format_brazilian_number(pmt01_data_filtered.min())}")
                    st.write(f"**Máximo:** {format_brazilian_number(pmt01_data_filtered.max())}")
                else:
                    st.info("Sem dados válidos (excluindo zeros)")

            with col2:
                st.markdown("#### 📈 Estatísticas - PMT 02")
                pmt02_data_filtered = df_plot.loc[df_plot['Peneira']=='PMT 02', indicador_selecionado]
                if not pmt02_data_filtered.empty:
                    st.write(f"**Média:** {format_brazilian_number(pmt02_data_filtered.mean())}")
                    st.write(f"**Mediana:** {format_brazilian_number(pmt02_data_filtered.median())}")
                    st.write(f"**Desvio Padrão:** {format_brazilian_number(pmt02_data_filtered.std())}")
                    st.write(f"**Mínimo:** {format_brazilian_number(pmt02_data_filtered.min())}")
                    st.write(f"**Máximo:** {format_brazilian_number(pmt02_data_filtered.max())}")
                else:
                    st.info("Sem dados válidos (excluindo zeros)")

# === ANÁLISE DE TENDÊNCIAS ===
st.markdown("---")
st.subheader("📈 Análise de Tendências Temporais")

if isinstance(df_boxplot, pd.DataFrame) and not df_boxplot.empty:
    indicadores_disponiveis = ['Fe', 'SiO2', 'Al2O3', 'TMP', '>31_5mm', '<0_15mm']

    indicador_tendencia = st.selectbox(
        "📊 Selecione um Indicador para Análise de Tendência",
        options=indicadores_disponiveis,
        key="tendencia_selector"
    )

    if indicador_tendencia:
        df_trend = df_boxplot.copy()
        df_trend[indicador_tendencia] = pd.to_numeric(df_trend[indicador_tendencia], errors='coerce')
        df_trend = df_trend.dropna(subset=[indicador_tendencia, 'Data'])

        if not df_trend.empty:
            # Gráfico de linha temporal
            fig_line = px.line(
                df_trend.sort_values('Data'),
                x='Data',
                y=indicador_tendencia,
                color='Peneira',
                title=f"📈 Evolução Temporal de {indicador_tendencia} - {mes_referencia}",
                markers=True
            )

            fig_line.update_layout(
                template='plotly_white',
                font=dict(size=12),
                title_font=dict(size=16),
                height=400,
                xaxis_title="Data",
                yaxis_title=f"{indicador_tendencia} ({'%' if indicador_tendencia in ['Fe', 'SiO2', 'Al2O3', '>31_5mm', '<0_15mm'] else 'mm' if indicador_tendencia == 'TMP' else ''})"
            )

            fig_line.update_yaxes(tickformat=',.2f')
            st.plotly_chart(fig_line, use_container_width=True)

            # === ANÁLISE DE VARIABILIDADE ===
            st.markdown("#### 🎯 Análise de Variabilidade")

            col1, col2 = st.columns(2)

            def filter_zeros_for_analysis(df, column):
                return df[df[column] > 0][column]

            with col1:
                pmt01_data_filtered = filter_zeros_for_analysis(df_trend[df_trend['Peneira'] == 'PMT 01'], indicador_tendencia)
                if not pmt01_data_filtered.empty and pmt01_data_filtered.mean() != 0:
                    pmt01_cv = (pmt01_data_filtered.std() / pmt01_data_filtered.mean()) * 100
                    st.metric("Coeficiente de Variação - PMT 01", format_percentage(pmt01_cv))
                else:
                    st.metric("Coeficiente de Variação - PMT 01", "N/D")

            with col2:
                pmt02_data_filtered = filter_zeros_for_analysis(df_trend[df_trend['Peneira'] == 'PMT 02'], indicador_tendencia)
                if not pmt02_data_filtered.empty and pmt02_data_filtered.mean() != 0:
                    pmt02_cv = (pmt02_data_filtered.std() / pmt02_data_filtered.mean()) * 100
                    st.metric("Coeficiente de Variação - PMT 02", format_percentage(pmt02_cv))
                else:
                    st.metric("Coeficiente de Variação - PMT 02", "N/D")

# === RODAPÉ ===
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; font-size: 0.8em;'>
        Dashboard de Qualidade - LHG Mining | Tupacery
    </div>
    """,
    unsafe_allow_html=True
)
