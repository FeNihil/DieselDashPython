"""Dashboard de Produção - Versão Ultra Comprimida"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from PIL import Image
import os, io, base64, zipfile
from cryptography.fernet import Fernet

# ========== CONFIG ==========
st.set_page_config(layout="wide", page_title="Dashboard de Produção Tupacery")
st.markdown("<style>.kpi-card{background:#262626;padding:1rem;border-radius:.5rem;border:1px solid #444}</style>", unsafe_allow_html=True)

def is_valid_xlsx(b): 
    try: return zipfile.is_zipfile(io.BytesIO(b))
    except: return False

# ========== CRYPTO ==========
HEX_KEY_STRING = st.secrets.get("HEX_KEY_STRING")
fernet = None
if HEX_KEY_STRING:
    try: fernet = Fernet(base64.urlsafe_b64encode(bytes.fromhex(HEX_KEY_STRING)))
    except ValueError as e: st.error(f"❌ Erro chave: {e}")
else: st.error("❌ HEX_KEY_STRING ausente")

# ========== CONSTANTS ==========
ARQUIVO_CRYPT = "Informativo_Operacional.encrypted"
LOGO_PATH = "Lhg-02.png"
ABA = "BD_Real"
COL_MAP = {
    '2025_Data': 'data',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 01_Lump': 'pm01_lump',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 01_Hemat': 'pm01_hematita',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 01_Sinter Feed\nNP': 'pm01_sinter',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 04_Lump': 'pm04_lump',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 04_Hemat': 'pm04_hematita',
    'PENEIRAMENTO MSC_Santa Cruz - Tupacery PM 04_Sinter Feed\nNP': 'pm04_sinter',
}
META_PM, META_LUMP_PM = 5000, 3240
META_SINTER_PM = META_PM - META_LUMP_PM
META_TOTAL, META_LUMP_TOTAL, META_SINTER_TOTAL = META_PM*2, META_LUMP_PM*2, META_SINTER_PM*2
ESTOQUE_INI, DATA_EST_INI = 189544, datetime(2025, 9, 16).date()

# ========== UTILS ==========
def fmt_br(n, dec=0): return f"{n:,.{dec}f}".replace(',', '.') if pd.notna(n) and n != 0 else "0"
def fmt_br_dec(n, dec=2): return f"{n:,.{dec}f}".replace(',', '|').replace('.', ',').replace('|', '.') if pd.notna(n) and n != 0 else "0"

# ========== I/O ==========
def ler_arquivo_local(path):
    if not os.path.exists(path): return None
    try:
        stat = os.stat(path)
        cache_key = f"{path}_{stat.st_size}_{stat.st_mtime}"
        if 'file_cache' not in st.session_state: st.session_state['file_cache'] = {}
        if cache_key in st.session_state['file_cache']: return st.session_state['file_cache'][cache_key]
        with open(path, "rb") as f: data = f.read()
        st.session_state['file_cache'] = {cache_key: data}
        return data
    except Exception as e: st.error(f"Erro {path}: {e}"); return None

def decrypt_data(cipher_bytes): 
    try: return fernet.decrypt(cipher_bytes)
    except Exception as e: st.error(f"Erro decrypt: {e}"); return None

@st.cache_data(ttl=300)
def load_excel(excel_bytes):
    try:
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=ABA, header=[0,1,2])
        df.columns = ['_'.join([str(c) for c in col if 'Unnamed' not in str(c)]).strip() for col in df.columns]
        df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})
        
        cols_keep = [col for col in COL_MAP.values() if col in df.columns]
        if 'data' not in cols_keep: st.error("Coluna 'data' não encontrada"); return None
        
        df = df[cols_keep].dropna(subset=['data'], how='all')
        df['data'] = pd.to_datetime(df['data'], errors='coerce')
        df = df.dropna(subset=['data'])
        
        for col in df.columns:
            if col != 'data': df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['total_dia'] = sum(df.get(col, 0) for col in ['pm01_lump', 'pm01_hematita', 'pm01_sinter', 'pm04_lump', 'pm04_hematita', 'pm04_sinter'])
        return df
    except Exception as e: st.error(f"Erro Excel: {e}"); return None

def carregar_dados():
    if not fernet: st.error("Fernet indisponível"); return None
    
    cipher_bytes = ler_arquivo_local(ARQUIVO_CRYPT)
    if cipher_bytes:
        st.success(f"✅ Dados: {ARQUIVO_CRYPT}")
        plain_bytes = decrypt_data(cipher_bytes)
        if plain_bytes:
            df = load_excel(plain_bytes)
            if df is not None:
                try: st.info(f"📅 Última atualização: {datetime.fromtimestamp(os.stat(ARQUIVO_CRYPT).st_mtime).strftime('%d/%m/%Y às %H:%M:%S')}")
                except: pass
                return df
    
    st.warning("⚠️ Arquivo não encontrado. Upload:")
    up = st.file_uploader("Arquivo criptografado", type=["encrypted", "bin", "xlsx"])
    if up:
        st.write(f"📁 {up.name} ({len(up_bytes := up.read())} bytes)")
        plain_bytes = decrypt_data(up_bytes)
        if plain_bytes:
            st.success("🔓 Descriptografado!")
            return load_excel(plain_bytes)
        elif is_valid_xlsx(up_bytes):
            st.warning("⚠️ Tentando XLSX...")
            df = load_excel(up_bytes)
            if df is not None: st.info("📈 Lido sem criptografia"); return df
    return None

# ========== UI ==========
try:
    if os.path.exists(LOGO_PATH): st.image(Image.open(LOGO_PATH), width=200)
    else: st.info("Logo não encontrada")
except: st.info("Falha logo")

st.title("Dashboard de Produção - Peneiras Móveis Tupacery")
st.markdown("---")

df = carregar_dados()
if df is None: st.error("❌ Não foi possível carregar dados"); st.stop()

# ========== SIDEBAR ==========
st.sidebar.header("Filtros de Análise")
if os.path.exists(LOGO_PATH): st.sidebar.image(LOGO_PATH, use_container_width=True)

df_prod = df[df['total_dia'] > 0]
if df_prod.empty: st.warning("Sem dias produtivos"); st.stop()

data_inicio, data_fim = datetime(2025, 8, 26).date(), df_prod['data'].max().date()
data_sel = st.sidebar.date_input("Período", value=(data_inicio, data_fim), min_value=data_inicio, max_value=df['data'].max().date(), format="DD/MM/YYYY")

st.sidebar.markdown("---")
st.sidebar.header("Metas Diárias")
st.sidebar.markdown("**Por Peneira:**")
st.sidebar.markdown(f"- Total: `{fmt_br(META_PM)} t`")
st.sidebar.markdown(f"- Lump: `{fmt_br(META_LUMP_PM)} t`")
st.sidebar.markdown(f"- Sinter: `{fmt_br(META_SINTER_PM)} t`")
st.sidebar.markdown("**Combinada:**")
st.sidebar.markdown(f"- Total: `{fmt_br(META_TOTAL)} t`")
st.sidebar.markdown(f"- Lump: `{fmt_br(META_LUMP_TOTAL)} t`")
st.sidebar.markdown(f"- Sinter: `{fmt_br(META_SINTER_TOTAL)} t`")
st.sidebar.markdown("---")
st.sidebar.info("🔄 Dados atualizados automaticamente")

# ========== FILTER DATA ==========
if isinstance(data_sel, tuple) and len(data_sel) == 2:
    inicio, fim = data_sel
    df_filt = df[(df['data'].dt.date >= inicio) & (df['data'].dt.date <= fim)].copy()
else: df_filt = df.copy()

if df_filt.empty: st.warning("Período sem dados"); st.stop()

# ========== CALCULATIONS ==========
df_filt['total_pm01'] = df_filt.get('pm01_lump', 0) + df_filt.get('pm01_hematita', 0) + df_filt.get('pm01_sinter', 0)
df_filt['total_pm04'] = df_filt.get('pm04_lump', 0) + df_filt.get('pm04_hematita', 0) + df_filt.get('pm04_sinter', 0)
df_filt['total_lump'] = df_filt.get('pm01_lump', 0) + df_filt.get('pm04_lump', 0)
df_filt['total_hematita'] = df_filt.get('pm01_hematita', 0) + df_filt.get('pm04_hematita', 0)
df_filt['total_sinter'] = df_filt.get('pm01_sinter', 0) + df_filt.get('pm04_sinter', 0)
df_filt['media_movel_7d'] = df_filt['total_dia'].rolling(7, min_periods=1).mean()

df_prod_filt = df_filt[df_filt['total_dia'] > 0].copy()
dias_prod_comb = len(df_prod_filt)

if dias_prod_comb > 0:
    dias_prod_pm01 = (df_prod_filt['total_pm01'] > 0).sum()
    dias_prod_pm04 = (df_prod_filt['total_pm04'] > 0).sum()
    
    prod_total_pm01, prod_total_pm04, prod_total_comb = df_prod_filt['total_pm01'].sum(), df_prod_filt['total_pm04'].sum(), df_prod_filt['total_dia'].sum()
    media_pm01 = prod_total_pm01 / dias_prod_pm01 if dias_prod_pm01 > 0 else 0
    media_pm04 = prod_total_pm04 / dias_prod_pm04 if dias_prod_pm04 > 0 else 0
    media_comb = prod_total_comb / dias_prod_comb
    
    ultimo_dia_df = df_prod_filt[df_prod_filt['data'].dt.date == df_prod_filt['data'].max().date()]
    prod_ult_pm01, prod_ult_pm04, prod_ult_comb = ultimo_dia_df['total_pm01'].sum(), ultimo_dia_df['total_pm04'].sum(), ultimo_dia_df['total_dia'].sum()
    
    meta_total_pm01, meta_total_pm04 = META_PM * dias_prod_pm01, META_PM * dias_prod_pm04
    meta_total_comb = meta_total_pm01 + meta_total_pm04
    
    ating_pm01 = (prod_total_pm01 / meta_total_pm01) * 100 if meta_total_pm01 > 0 else 0
    ating_pm04 = (prod_total_pm04 / meta_total_pm04) * 100 if meta_total_pm04 > 0 else 0
    ating_comb = (prod_total_comb / meta_total_comb) * 100 if meta_total_comb > 0 else 0
else:
    prod_total_pm01 = prod_total_pm04 = prod_total_comb = 0
    media_pm01 = media_pm04 = media_comb = 0
    prod_ult_pm01 = prod_ult_pm04 = prod_ult_comb = 0
    ating_pm01 = ating_pm04 = ating_comb = 0

# ========== STOCK CALC ==========
df_consumo = df[df['data'].dt.date > DATA_EST_INI]
prod_consumida = df_consumo['total_dia'].sum()
estoque_atual = ESTOQUE_INI - prod_consumida
ritmo_atual = df_filt['media_movel_7d'].iloc[-1] if not df_filt.empty else 0
dias_restantes = (estoque_atual / ritmo_atual) if ritmo_atual > 0 else 0

# ========== DASHBOARD ==========
st.subheader("Painel de Indicadores (KPIs)")
st.markdown("##### Visão Geral (Combinado)")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Produção Total no Período", f"{fmt_br(prod_total_comb)} t")
col2.metric("Média Diária (dias produtivos)", f"{fmt_br(media_comb)} t")
col3.metric(f"Produção do Último Dia ({df_prod_filt['data'].max().strftime('%d/%m') if dias_prod_comb > 0 else 'N/A'})", f"{fmt_br(prod_ult_comb)} t")
col4.metric("Atingimento Meta Combinada", f"{ating_comb:.1f}%".replace('.', ','))

st.markdown("---")
st.markdown("##### Desempenho Individual (Por Peneira)")

def render_pm_metrics(title, media, ultimo, ating):
    with st.container(border=True):
        st.markdown(f"<h6 style='text-align: center;'>{title}</h6>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Média Diária {title[-4:]}", f"{fmt_br(media)} t")
        c2.metric(f"Último Dia {title[-4:]}", f"{fmt_br(ultimo)} t")
        c3.metric(f"Meta {title[-4:]}", f"{ating:.1f}%".replace('.', ','))

col1, col2 = st.columns(2)
with col1: render_pm_metrics("Peneira Móvel 01", media_pm01, prod_ult_pm01, ating_pm01)
with col2: render_pm_metrics("Peneira Móvel 04", media_pm04, prod_ult_pm04, ating_pm04)

st.markdown("---")
st.subheader("Previsão de Estoque & Ritmo Operacional")
col1, col2, col3 = st.columns(3)
col1.metric("Estoque Atual (Aprox.)", f"{fmt_br(estoque_atual)} t", f"-{fmt_br(prod_consumida)} t desde {DATA_EST_INI.strftime('%d/%m')}")
col2.metric("Ritmo Atual (Média Móvel 7d)", f"{fmt_br(ritmo_atual)} t/dia")
col3.metric("Previsão de Dias Restantes", f"{dias_restantes:.1f} dias".replace('.', ','))

st.markdown("---")
st.subheader("Atingimento de Metas Individuais no Período")

def create_gauge(value, threshold, title, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, title={'text': title},
        gauge={'axis': {'range': [None, threshold * 1.1]}, 'threshold': {'line': {'color': color, 'width': 4}, 'thickness': 0.75, 'value': threshold}, 'bar': {'color': color}}
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, b=20, t=50), paper_bgcolor="rgba(0,0,0,0)", font={'color': "var(--text-color)"})
    return fig

col1, col2 = st.columns(2)
with col1: st.plotly_chart(create_gauge(prod_total_pm01, META_PM * max(1, dias_prod_pm01), "Meta Total PM 01", "#f47c20"), use_container_width=True)
with col2: st.plotly_chart(create_gauge(prod_total_pm04, META_PM * max(1, dias_prod_pm04), "Meta Total PM 04", "#5A99E2"), use_container_width=True)

st.markdown("---")
st.subheader("Evolução da Produção Diária Empilhada por Produto")
fig_prod = px.bar(df_filt, x='data', y=['total_lump', 'total_sinter', 'total_hematita'], title="Produção Diária Empilhada (PM01 + PM04)",
                  labels={'value': 'Produção (t)', 'variable': 'Produto', 'data': 'Data'},
                  color_discrete_map={'total_lump': '#f47c20', 'total_sinter': '#5A99E2', 'total_hematita': '#A9A9A9'})
fig_prod.add_trace(go.Scatter(x=df_filt['data'], y=df_filt['media_movel_7d'], mode='lines', name='Média Móvel 7 Dias', line=dict(color='yellow', width=3)))
fig_prod.update_layout(template='plotly_dark')
st.plotly_chart(fig_prod, use_container_width=True)

st.markdown("---")
st.subheader("Análise Detalhada por Peneira (Mix de Produtos)")

def create_pie(values, title, colors):
    fig = px.pie(values=values, names=['Lump', 'Hematita', 'Sinter Feed'], hole=0.4, color_discrete_sequence=colors)
    fig.update_layout(template='plotly_dark', showlegend=title == "PM 04")
    return fig

col1, col2 = st.columns(2)
with col1:
    st.markdown("<h5 style='text-align: center;'>Mix de Produtos - PM 01</h5>", unsafe_allow_html=True)
    pm01_vals = [df_prod_filt.get(f'pm01_{p}', pd.Series(dtype=float)).sum() for p in ['lump', 'hematita', 'sinter']]
    st.plotly_chart(create_pie(pm01_vals, "PM 01", ['#f47c20', '#ff9a51', '#ffb885']), use_container_width=True)

with col2:
    st.markdown("<h5 style='text-align: center;'>Mix de Produtos - PM 04</h5>", unsafe_allow_html=True)
    pm04_vals = [df_prod_filt.get(f'pm04_{p}', pd.Series(dtype=float)).sum() for p in ['lump', 'hematita', 'sinter']]
    st.plotly_chart(create_pie(pm04_vals, "PM 04", ['#5A99E2', '#87B5ED', '#B4D1F5']), use_container_width=True)

# ========== DETAILED STATS ==========
with st.expander("Clique para ver Estatísticas Detalhadas da Produção"):
    def tendencia_semana(serie): 
        if len(serie) < 14: return 0.0
        ult7, penult7 = serie.iloc[-7:].mean(), serie.iloc[-14:-7].mean()
        return ((ult7 - penult7) / penult7 * 100) if penult7 > 0 else 0.0
    
    ritmo_pm01_7d = df_prod_filt['total_pm01'].rolling(7, min_periods=1).mean().iloc[-1] if not df_prod_filt.empty else 0
    ritmo_pm04_7d = df_prod_filt['total_pm04'].rolling(7, min_periods=1).mean().iloc[-1] if not df_prod_filt.empty else 0
    
    tend_pm01 = tendencia_semana(df_prod_filt['total_pm01'])
    tend_pm04 = tendencia_semana(df_prod_filt['total_pm04'])
    tend_comb = tendencia_semana(df_prod_filt['total_dia'])
    
    proj_adic_pm01 = ritmo_pm01_7d * dias_restantes if ritmo_pm01_7d > 0 and dias_restantes > 0 else 0
    proj_adic_pm04 = ritmo_pm04_7d * dias_restantes if ritmo_pm04_7d > 0 and dias_restantes > 0 else 0
    proj_adic_comb = ritmo_atual * dias_restantes if ritmo_atual > 0 and dias_restantes > 0 else 0
    
    proj_total_pm01, proj_total_pm04, proj_total_comb = prod_total_pm01 + proj_adic_pm01, prod_total_pm04 + proj_adic_pm04, prod_total_comb + proj_adic_comb
    proj_ating_pm01 = (proj_total_pm01 / meta_total_pm01 * 100) if meta_total_pm01 > 0 else 0
    proj_ating_pm04 = (proj_total_pm04 / meta_total_pm04 * 100) if meta_total_pm04 > 0 else 0
    proj_ating_comb = (proj_total_comb / meta_total_comb * 100) if meta_total_comb > 0 else 0
    
    dados = [
        ['Combinado', prod_total_comb, meta_total_comb, media_comb, ritmo_atual, tend_comb, ating_comb, proj_adic_comb, proj_total_comb, proj_ating_comb],
        ['PM01', prod_total_pm01, meta_total_pm01, media_pm01, ritmo_pm01_7d, tend_pm01, ating_pm01, proj_adic_pm01, proj_total_pm01, proj_ating_pm01],
        ['PM04', prod_total_pm04, meta_total_pm04, media_pm04, ritmo_pm04_7d, tend_pm04, ating_pm04, proj_adic_pm04, proj_total_pm04, proj_ating_pm04],
    ]
    
    linhas = []
    for linha in dados:
        ent, prod, meta, med, ritmo, tend, ating, proj_ad, proj_tot, proj_at = linha
        linhas.append({
            'Entidade': ent, 'Produção Total (t)': fmt_br(prod), 'Meta Total (t)': fmt_br(meta),
            'Média Diária (t/dia)': fmt_br(med), 'Ritmo MM7 (t/dia)': fmt_br(ritmo),
            'Tendência 7d vs 7d ant.': f"{tend:.1f}%".replace('.', ','), 'Atingimento Meta (%)': f"{ating:.1f}%".replace('.', ','),
            'Proj. Adicional (t)': fmt_br(proj_ad), 'Proj. Total (t)': fmt_br(proj_tot), 'Proj. Ating. (%)': f"{proj_at:.1f}%".replace('.', ',')
        })
    
    st.markdown("#### Resumo Estatístico por Entidade")
    st.dataframe(pd.DataFrame(linhas), use_container_width=True)