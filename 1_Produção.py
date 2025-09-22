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

# =========================
# Configuração de página
# =========================
st.set_page_config(layout="wide", page_title="Dashboard de Produção Tuypacery")
st.markdown(
    "<style>.kpi-card {background-color: #262626; padding: 1rem; border-radius: 0.5rem; border: 1px solid #444;}</style>",
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
NOME_ARQUIVO_SALVO = "Informativo_Operacional_2025.xlsx"  # criptografado (bytes criptografados)
CAMINHO_LOGO = "Lhg-02.png"  # colocar na raiz do repo ou ajuste caminho relativo

NOME_ABA = "BD_Real"
MAPEAMENTO_COLUNAS = {
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

# =========================
# Utilidades de formatação
# =========================
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

# =========================
# I/O: carregar bytes criptografados e descriptografar
# =========================
@st.cache_data(ttl=3600)
def ler_bytes_arquivo_local(caminho: str) -> bytes | None:
    if not os.path.exists(caminho):
        return None
    with open(caminho, "rb") as f:
        return f.read()

def descriptografar_bytes(cipher_bytes: bytes, fernet_obj: Fernet) -> bytes | None:
    try:
        return fernet_obj.decrypt(cipher_bytes)
    except Exception as e:
        st.error(f"Erro ao descriptografar o arquivo: {e}")
        return None

@st.cache_data(ttl=3600)
def carregar_excel_em_df(excel_bytes: bytes) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=NOME_ABA, header=[0, 1, 2])
        novas_colunas = [
            '_'.join([str(c) for c in col if 'Unnamed' not in str(c)]).strip()
            for col in df.columns
        ]
        df.columns = novas_colunas
        df = df.rename(columns={k: v for k, v in MAPEAMENTO_COLUNAS.items() if k in df.columns})

        colunas_necessarias = list(MAPEAMENTO_COLUNAS.values())
        colunas_a_manter = [col for col in colunas_necessarias if col in df.columns]
        if 'data' not in colunas_a_manter:
            st.error("A coluna 'data' não foi encontrada. Verifique o mapeamento de colunas.")
            return None

        df = df[colunas_a_manter]
        df.dropna(subset=['data'], how='all', inplace=True)
        df['data'] = pd.to_datetime(df['data'], errors='coerce')
        df.dropna(subset=['data'], inplace=True)

        colunas_producao = [col for col in df.columns if col != 'data']
        for col in colunas_producao:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['total_dia'] = (
            df.get('pm01_lump', 0) + df.get('pm01_hematita', 0) + df.get('pm01_sinter', 0) +
            df.get('pm04_lump', 0) + df.get('pm04_hematita', 0) + df.get('pm04_sinter', 0)
        )
        return df
    except Exception as e:
        st.error(f"Erro ao ler/processar a planilha: {e}")
        return None

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

st.title("Dashboard de Produção - Peneiras Móveis Tuypacery")
st.markdown("---")

# =========================
# Entrada de dados: prioriza arquivo no repo; fallback uploader
# =========================
def tentar_carregar_df() -> pd.DataFrame | None:
    if fernet is None:
        return None

    # 1) Tentar ler bytes criptografados do arquivo no repo
    cipher_bytes_repo = ler_bytes_arquivo_local(NOME_ARQUIVO_SALVO)
    if cipher_bytes_repo:
        plain_bytes = descriptografar_bytes(cipher_bytes_repo, fernet)
        if plain_bytes:
            return carregar_excel_em_df(plain_bytes)

    # 2) Fallback: permitir upload do arquivo criptografado
    st.info("Carregue o arquivo Excel criptografado (mesma chave) via upload.")
    up = st.file_uploader("Selecione o arquivo Excel criptografado", type=["xlsx", "bin"])
    if up is not None:
        cipher_bytes_upload = up.read()
        plain_bytes = descriptografar_bytes(cipher_bytes_upload, fernet)
        if plain_bytes:
            return carregar_excel_em_df(plain_bytes)
    return None

if 'df_producao' not in st.session_state:
    st.session_state['df_producao'] = tentar_carregar_df()

if st.button("Recarregar dados"):
    st.session_state['df_producao'] = tentar_carregar_df()

if st.session_state['df_producao'] is None:
    st.warning("Não foi possível carregar os dados. Verifique o arquivo criptografado e a chave em secrets.")
    st.stop()

df = st.session_state['df_producao']

# =========================
# Sidebar e filtros
# =========================
st.sidebar.header("Filtros de Análise")
if os.path.exists(CAMINHO_LOGO):
    st.sidebar.image(CAMINHO_LOGO, use_container_width=True)

df_produtivo_geral = df[df['total_dia'] > 0]
if df_produtivo_geral.empty:
    st.warning("Sem dias produtivos encontrados.")
    st.stop()

data_inicio_operacao = datetime(2025, 8, 26).date()
data_fim_dados = df_produtivo_geral['data'].max().date()
data_selecionada = st.sidebar.date_input(
    "Selecione o Período",
    value=(data_inicio_operacao, data_fim_dados),
    min_value=data_inicio_operacao,
    max_value=df['data'].max().date(),
    format="DD/MM/YYYY"
)

st.sidebar.markdown("---")
st.sidebar.header("Metas Diárias")
st.sidebar.markdown("**Por Peneira:**")
st.sidebar.markdown(f"- Total: `{format_number_br_no_decimals(META_DIARIA_PM)} t`")
st.sidebar.markdown(f"- Lump: `{format_number_br_no_decimals(META_DIARIA_LUMP_PM)} t`")
st.sidebar.markdown(f"- Sinter: `{format_number_br_no_decimals(META_DIARIA_SINTER_PM)} t`")
st.sidebar.markdown("**Combinada:**")
st.sidebar.markdown(f"- Total: `{format_number_br_no_decimals(META_DIARIA_TOTAL_COMBINADA)} t`")
st.sidebar.markdown(f"- Lump: `{format_number_br_no_decimals(META_DIARIA_LUMP_COMBINADA)} t`")
st.sidebar.markdown(f"- Sinter: `{format_number_br_no_decimals(META_DIARIA_SINTER_COMBINADA)} t`")

if isinstance(data_selecionada, tuple) and len(data_selecionada) == 2:
    data_inicio_filtro, data_fim_filtro = data_selecionada
    df_filtrado = df[(df['data'].dt.date >= data_inicio_filtro) & (df['data'].dt.date <= data_fim_filtro)].copy()
else:
    df_filtrado = df.copy()

# =========================
# Cálculos e KPIs
# =========================
if not df_filtrado.empty:
    df_filtrado['total_pm01'] = df_filtrado.get('pm01_lump', 0) + df_filtrado.get('pm01_hematita', 0) + df_filtrado.get('pm01_sinter', 0)
    df_filtrado['total_pm04'] = df_filtrado.get('pm04_lump', 0) + df_filtrado.get('pm04_hematita', 0) + df_filtrado.get('pm04_sinter', 0)
    df_filtrado['total_lump'] = df_filtrado.get('pm01_lump', 0) + df_filtrado.get('pm04_lump', 0)
    df_filtrado['total_hematita'] = df_filtrado.get('pm01_hematita', 0) + df_filtrado.get('pm04_hematita', 0)
    df_filtrado['total_sinter'] = df_filtrado.get('pm01_sinter', 0) + df_filtrado.get('pm04_sinter', 0)
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
        prod_total_pm01 = prod_total_pm04 = prod_total_combinada = 0
        media_pm01 = media_pm04 = media_combinada = 0
        prod_ultimo_dia_pm01 = prod_ultimo_dia_pm04 = prod_ultimo_dia_combinada = 0
        atingimento_pm01 = atingimento_pm04 = atingimento_combinado = 0

    # =========================
    # Visualizações
    # =========================
    st.subheader("Painel de Indicadores (KPIs)")
    st.markdown("##### Visão Geral (Combinado)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Produção Total no Período", f"{format_number_br_no_decimals(prod_total_combinada)} t")
    col2.metric("Média Diária (dias produtivos)", f"{format_number_br_no_decimals(media_combinada)} t")
    col3.metric(
        f"Produção do Último Dia ({df_produtivo['data'].max().strftime('%d/%m') if dias_produtivos_combinado > 0 else 'N/A'})",
        f"{format_number_br_no_decimals(prod_ultimo_dia_combinada)} t"
    )
    col4.metric("Atingimento Meta Combinada", f"{atingimento_combinado:.1f}%".replace('.', ','))

    st.markdown("---")
    st.markdown("##### Desempenho Individual (Por Peneira)")
    kpicol1, kpicol2 = st.columns(2)
    with kpicol1:
        with st.container(border=True):
            st.markdown("<h6 style='text-align: center;'>Peneira Móvel 01</h6>", unsafe_allow_html=True)
            subcol1, subcol2, subcol3 = st.columns(3)
            subcol1.metric("Média Diária PM01", f"{format_number_br_no_decimals(media_pm01)} t")
            subcol2.metric("Último Dia PM01", f"{format_number_br_no_decimals(prod_ultimo_dia_pm01)} t")
            subcol3.metric("Meta PM01", f"{atingimento_pm01:.1f}%".replace('.', ','))
    with kpicol2:
        with st.container(border=True):
            st.markdown("<h6 style='text-align: center;'>Peneira Móvel 04</h6>", unsafe_allow_html=True)
            subcol1, subcol2, subcol3 = st.columns(3)
            subcol1.metric("Média Diária PM04", f"{format_number_br_no_decimals(media_pm04)} t")
            subcol2.metric("Último Dia PM04", f"{format_number_br_no_decimals(prod_ultimo_dia_pm04)} t")
            subcol3.metric("Meta PM04", f"{atingimento_pm04:.1f}%".replace('.', ','))

    st.markdown("---")

    st.subheader("Previsão de Estoque & Ritmo Operacional")
    df_consumo = df[df['data'].dt.date > DATA_ESTOQUE_INICIAL]
    producao_consumida = df_consumo['total_dia'].sum()
    estoque_atual = ESTOQUE_INICIAL - producao_consumida
    ritmo_atual = df_filtrado['media_movel_7d'].iloc[-1] if not df_filtrado.empty else 0
    dias_restantes = (estoque_atual / ritmo_atual) if ritmo_atual > 0 else 0

    col_prev1, col_prev2, col_prev3 = st.columns(3)
    col_prev1.metric(
        "Estoque Atual (Aprox.)",
        f"{format_number_br_no_decimals(estoque_atual)} t",
        f"-{format_number_br_no_decimals(producao_consumida)} t desde {DATA_ESTOQUE_INICIAL.strftime('%d/%m')}"
    )
    col_prev2.metric("Ritmo Atual (Média Móvel 7d)", f"{format_number_br_no_decimals(ritmo_atual)} t/dia")
    col_prev3.metric("Previsão de Dias Restantes", f"{dias_restantes:.1f} dias".replace('.', ','))

    st.markdown("---")

    st.subheader("Atingimento de Metas Individuais no Período")
    meta_chart1, meta_chart2 = st.columns(2)
    with meta_chart1:
        fig_meta_pm01 = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=prod_total_pm01,
                title={'text': "Meta Total PM 01"},
                gauge={
                    'axis': {'range': [None, (META_DIARIA_PM * max(1, (df_produtivo['total_pm01'] > 0).sum())) * 1.1]},
                    'threshold': {
                        'line': {'color': "#f47c20", 'width': 4},
                        'thickness': 0.75,
                        'value': META_DIARIA_PM * (df_produtivo['total_pm01'] > 0).sum()
                    },
                    'bar': {'color': "#f47c20"}
                }
            )
        )
        fig_meta_pm01.update_layout(height=250, margin=dict(l=20, r=20, b=20, t=50), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
        st.plotly_chart(fig_meta_pm01, use_container_width=True)

    with meta_chart2:
        NOVO_AZUL = "#5A99E2"
        fig_meta_pm04 = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=prod_total_pm04,
                title={'text': "Meta Total PM 04"},
                gauge={
                    'axis': {'range': [None, (META_DIARIA_PM * max(1, (df_produtivo['total_pm04'] > 0).sum())) * 1.1]},
                    'threshold': {
                        'line': {'color': NOVO_AZUL, 'width': 4},
                        'thickness': 0.75,
                        'value': META_DIARIA_PM * (df_produtivo['total_pm04'] > 0).sum()
                    },
                    'bar': {'color': NOVO_AZUL}
                }
            )
        )
        fig_meta_pm04.update_layout(height=250, margin=dict(l=20, r=20, b=20, t=50), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
        st.plotly_chart(fig_meta_pm04, use_container_width=True)

    st.markdown("---")

    st.subheader("Evolução da Produção Diária Empilhada por Produto")
    NOVO_AZUL = "#5A99E2"
    fig_producao = px.bar(
        df_filtrado,
        x='data',
        y=['total_lump', 'total_sinter', 'total_hematita'],
        title="Produção Diária Empilhada (PM01 + PM04)",
        labels={'value': 'Produção (t)', 'variable': 'Produto', 'data': 'Data'},
        color_discrete_map={'total_lump': '#f47c20', 'total_sinter': NOVO_AZUL, 'total_hematita': '#A9A9A9'}
    )
    fig_producao.add_trace(
        go.Scatter(
            x=df_filtrado['data'],
            y=df_filtrado['media_movel_7d'],
            mode='lines',
            name='Média Móvel 7 Dias',
            line=dict(color='yellow', width=3)
        )
    )
    fig_producao.update_layout(template='plotly_dark')
    st.plotly_chart(fig_producao, use_container_width=True)

    st.markdown("---")

    st.subheader("Análise Detalhada por Peneira (Mix de Produtos)")
    col_pm1, col_pm2 = st.columns(2)
    with col_pm1:
        st.markdown("<h5 style='text-align: center;'>Mix de Produtos - PM 01</h5>", unsafe_allow_html=True)
        pm01_somas = [
            df_produtivo.get('pm01_lump', pd.Series(dtype=float)).sum(),
            df_produtivo.get('pm01_hematita', pd.Series(dtype=float)).sum(),
            df_produtivo.get('pm01_sinter', pd.Series(dtype=float)).sum()
        ]
        produtos_nomes = ['Lump', 'Hematita', 'Sinter Feed']
        fig_pizza_pm01 = px.pie(values=pm01_somas, names=produtos_nomes, hole=0.4,
                                color_discrete_sequence=['#f47c20', '#ff9a51', '#ffb885'])
        fig_pizza_pm01.update_layout(template='plotly_dark', showlegend=False)
        st.plotly_chart(fig_pizza_pm01, use_container_width=True)

    with col_pm2:
        st.markdown("<h5 style='text-align: center;'>Mix de Produtos - PM 04</h5>", unsafe_allow_html=True)
        pm04_somas = [
            df_produtivo.get('pm04_lump', pd.Series(dtype=float)).sum(),
            df_produtivo.get('pm04_hematita', pd.Series(dtype=float)).sum(),
            df_produtivo.get('pm04_sinter', pd.Series(dtype=float)).sum()
        ]
        fig_pizza_pm04 = px.pie(values=pm04_somas, names=produtos_nomes, hole=0.4,
                                color_discrete_sequence=[NOVO_AZUL, '#87B5ED', '#B4D1F5'])
        fig_pizza_pm04.update_layout(template='plotly_dark')
        st.plotly_chart(fig_pizza_pm04, use_container_width=True)

    with st.expander("Clique para ver Estatísticas Detalhadas da Produção"):
        df_stats = df_produtivo[['total_dia', 'total_pm01', 'total_pm04']].copy()
        df_stats.columns = ['Total Combinado', 'Total PM01', 'Total PM04']
        df_stats_formatted = df_stats.describe().T
        for col in df_stats_formatted.columns:
            df_stats_formatted[col] = df_stats_formatted[col].apply(lambda x: format_number_br_with_decimals(x, 2))
        st.dataframe(df_stats_formatted)
else:
    st.warning("Não há dias produtivos para o período selecionado.")
