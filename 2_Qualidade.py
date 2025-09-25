"""Dashboard de Qualidade - Versão Comprimida"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from PIL import Image
import os, io, base64, zipfile, re, unicodedata
from cryptography.fernet import Fernet

# ========== CONFIGURAÇÃO ==========
st.set_page_config(layout="wide", page_title="Dashboard de Qualidade Tupacery")
for key in ['mes_referencia', 'df_boxplot', 'df_qualidade_dia', 'df_qualidade_media']:
    if key not in st.session_state: st.session_state[key] = None

# ========== CRIPTOGRAFIA ==========
HEX_KEY_STRING = st.secrets.get("HEX_KEY_STRING")
fernet = None
if HEX_KEY_STRING:
    try:
        fernet = Fernet(base64.urlsafe_b64encode(bytes.fromhex(HEX_KEY_STRING)))
    except ValueError as e:
        st.error(f"❌ Erro na chave: {e}")
else:
    st.error("❌ HEX_KEY_STRING ausente em secrets")

# ========== CONSTANTES ==========
ARQUIVO_CRYPT = "Relatorio_Qualidade.encrypted"
LOGO_PATH = "Lhg-02.png"
ABA_QUALIDADE = "RESUMO GR"
INDICADORES = ['Fe', 'SiO2', 'Al2O3', 'TMP', '>31_5mm', '<0_15mm']

# ========== FUNÇÕES UTILITÁRIAS ==========
def fmt_num(val, dec=2): return f"{float(val):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(val) else "N/D"
def fmt_pct(val): return f"{fmt_num(val, 2)}%" if pd.notna(val) else "N/D"
def fmt_med(val, unit="mm"): return f"{fmt_num(val, 2)} {unit}" if pd.notna(val) else "N/D"

def norm_text(x):
    x = ''.join(c for c in unicodedata.normalize('NFD', str(x).strip().lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', x.replace('%', '').replace('(', '').replace(')', '').replace(',', '.'))

def map_col(col):
    s = norm_text(col)
    mappings = {r'\bfe\b': 'Fe', r'sio2|si o2|silica': 'SiO2', r'al2o3|alumina': 'Al2O3', 
                r'\bp\b': 'P', r'\bmn\b': 'Mn', r'ton': 'Ton', r'loi': 'LOI', r'\bmm\b': 'TMP',
                r'(\+|>) *31(\.|,)5': '>31_5mm', r'- *12(?!.*umidade)': '_col1', r'- *6(\.|,)3': '_col2',
                r'total': 'TOTAL', r'data': 'Data'}
    for pattern, replacement in mappings.items():
        if re.search(pattern, s): return replacement
    return col.strip()

def is_valid_xlsx(b): 
    try: return zipfile.is_zipfile(io.BytesIO(b))
    except: return False

# ========== I/O FUNCTIONS ==========
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
    except Exception as e: st.error(f"Erro ao ler {path}: {e}"); return None

def decrypt_data(cipher_bytes): 
    try: return fernet.decrypt(cipher_bytes)
    except Exception as e: st.error(f"Erro decrypt: {e}"); return None

# ========== PROCESSAMENTO DE DADOS ==========
def flatten_cols(df):
    if not isinstance(df.columns, pd.MultiIndex): return df
    new_cols = []
    for col in df.columns:
        if isinstance(col, tuple):
            a, b = col
            a_txt = '' if pd.isna(a) else str(a).strip()
            b_txt = '' if pd.isna(b) else str(b).strip()
            new_cols.append(b_txt if b_txt else a_txt if a_txt else f"{a}_{b}")
        else: new_cols.append(str(col))
    df.columns = new_cols
    return df

def process_block(df_block):
    df_block = flatten_cols(df_block)
    df_block.rename(columns={c: map_col(c) for c in df_block.columns}, inplace=True)
    
    # Fix duplicate columns
    cols, seen, new_cols = list(df_block.columns), {}, []
    for c in cols:
        if c in seen: seen[c] += 1; new_cols.append(f"{c}_{seen[c]}")
        else: seen[c] = 1; new_cols.append(c)
    df_block.columns = new_cols
    
    # Find date column
    date_col = next((c for c in df_block.columns if 'data' in norm_text(c)), df_block.columns[0])
    df_block.rename(columns={date_col: 'Data'}, inplace=True)
    
    # Convert types
    df_block['Data'] = pd.to_datetime(df_block['Data'], errors='coerce')
    for col in df_block.columns:
        if col != 'Data': df_block[col] = pd.to_numeric(df_block[col], errors='coerce')
    
    # Calculate <0_15mm
    if '_col1' in df_block.columns and '_col2' in df_block.columns:
        df_block['<0_15mm'] = df_block['_col1'].fillna(0) + df_block['_col2'].fillna(0)
    
    return df_block

@st.cache_data(ttl=300)
def load_quality_data(excel_bytes):
    try:
        df_raw = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=ABA_QUALIDADE, header=[0, 1], nrows=34, engine='openpyxl')
        
        # Detect blocks (simplified)
        blocks = [(260, 267), (709, 716)]  # Default positions
        try:
            lvl1 = [norm_text(x) if not pd.isna(x) else '' for x in df_raw.columns.get_level_values(1)]
            starts = [i for i, v in enumerate(lvl1) if 'data' in v]
            if len(starts) >= 2:
                blocks = [(starts[0], starts[1]-1), (starts[1], df_raw.shape[1]-1)][:2]
        except: pass
        
        # Process blocks
        s1, e1 = blocks[0]; s2, e2 = blocks[1]
        pmt01 = process_block(df_raw.iloc[:, s1:e1+1].copy())
        pmt02 = process_block(df_raw.iloc[:, s2:e2+1].copy())
        
        # Find last valid date
        def last_valid_date(df):
            if 'Ton' in df.columns:
                mask = pd.to_numeric(df['Ton'], errors='coerce').fillna(0) > 0
                if mask.any(): return df.loc[mask, 'Data'].max()
            numeric_cols = [c for c in df.columns if c != 'Data']
            if numeric_cols:
                mask = df[numeric_cols].notna().any(axis=1)
                if mask.any(): return df.loc[mask, 'Data'].max()
            return df['Data'].dropna().max() if df['Data'].notna().any() else pd.NaT
        
        ultimo_dia = max([d for d in [last_valid_date(pmt01), last_valid_date(pmt02)] if not pd.isna(d)])
        
        # Get data for last day
        def get_day_data(df, date):
            try:
                mask = df['Data'] == date
                if mask.any(): return df.loc[mask].iloc[0].drop(labels='Data')
            except: pass
            if 'Ton' in df.columns:
                try:
                    mask = pd.to_numeric(df['Ton'], errors='coerce').fillna(0) > 0
                    if mask.any(): return df.loc[mask].iloc[-1].drop(labels='Data')
                except: pass
            numeric_cols = [c for c in df.columns if c != 'Data']
            mask = df[numeric_cols].notna().any(axis=1)
            return df.loc[mask].iloc[-1].drop(labels='Data') if mask.any() else pd.Series([pd.NA] * len(numeric_cols), index=numeric_cols)
        
        row1, row2 = get_day_data(pmt01, ultimo_dia), get_day_data(pmt02, ultimo_dia)
        
        # Create day DataFrame
        dia_data = {ind: [row1.get(ind, pd.NA), row2.get(ind, pd.NA)] for ind in INDICADORES}
        dia = pd.DataFrame(dia_data, index=['PMT 01', 'PMT 02']).T
        dia.loc['PRODUTO_DIA'] = [ultimo_dia, ultimo_dia]
        
        # Calculate monthly means (excluding zeros)
        def calc_mean(df):
            subset = df[pd.to_numeric(df.get('Ton', pd.Series([0])), errors='coerce').fillna(0) > 0] if 'Ton' in df.columns else df[df[[c for c in df.columns if c != 'Data']].notna().any(axis=1)]
            means = {}
            for ind in INDICADORES:
                if ind in subset.columns:
                    col = pd.to_numeric(subset[ind], errors='coerce').dropna()
                    col = col[col != 0]
                    means[ind] = col.mean() if not col.empty else pd.NA
                else: means[ind] = pd.NA
            return pd.Series(means)
        
        media = pd.DataFrame({'PMT 01': calc_mean(pmt01), 'PMT 02': calc_mean(pmt02)})
        
        # Boxplot data
        pmt01['Peneira'] = 'PMT 01'; pmt02['Peneira'] = 'PMT 02'
        boxplot_data = pd.concat([pmt01, pmt02], ignore_index=True)[lambda x: x['Data'].notna()].reset_index(drop=True)
        
        # Format month
        meses = {'01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril', '05': 'Maio', '06': 'Junho',
                '07': 'Julho', '08': 'Agosto', '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro'}
        mm, yy = ultimo_dia.strftime('%m'), ultimo_dia.strftime('%Y')
        mes_pt = f"{meses.get(mm, mm)}/{yy}"
        
        return dia, media, boxplot_data, mes_pt
    except Exception as e: st.error(f"Erro ao processar dados: {e}"); return None, None, None, None

# ========== CARREGAMENTO DE DADOS ==========
def load_data():
    if not fernet: st.error("Fernet indisponível"); return None, None, None, None
    
    # Try encrypted file from repo
    cipher_bytes = ler_arquivo_local(ARQUIVO_CRYPT)
    if cipher_bytes:
        st.success(f"✅ Dados carregados: {ARQUIVO_CRYPT}")
        plain_bytes = decrypt_data(cipher_bytes)
        if plain_bytes:
            result = load_quality_data(plain_bytes)
            if result[0] is not None:
                try: st.info(f"📅 Última atualização: {datetime.fromtimestamp(os.stat(ARQUIVO_CRYPT).st_mtime).strftime('%d/%m/%Y às %H:%M:%S')}")
                except: pass
                return result
    
    # Fallback: file upload
    st.warning("⚠️ Arquivo não encontrado. Faça upload:")
    up = st.file_uploader("Arquivo criptografado", type=["encrypted", "bin", "xlsx"], key="qual_up")
    if up:
        st.write(f"📁 {up.name} ({len(up_bytes := up.read())} bytes)")
        plain_bytes = decrypt_data(up_bytes)
        if plain_bytes:
            st.success("🔓 Descriptografado!")
            result = load_quality_data(plain_bytes)
            return result if result[0] is not None else (None, None, None, None)
        elif is_valid_xlsx(up_bytes):
            st.warning("⚠️ Tentando como XLSX...")
            result = load_quality_data(up_bytes)
            if result[0] is not None: st.info("📈 Lido sem criptografia"); return result
    return None, None, None, None

# ========== INTERFACE ==========
# Logo
try:
    if os.path.exists(LOGO_PATH): st.image(Image.open(LOGO_PATH), width=200)
    else: st.info("Logo não encontrada")
except: st.info("Falha ao carregar logo")

st.title("Dashboard de Qualidade - Peneiras Móveis Tupacery")
st.markdown("---")

# Load data
df_dia, df_media, df_box, mes_ref = load_data()
if df_dia is None: st.error("❌ Não foi possível carregar dados"); st.stop()

# Store in session
for k, v in zip(['df_qualidade_dia', 'df_qualidade_media', 'df_boxplot', 'mes_referencia'], [df_dia, df_media, df_box, mes_ref]):
    st.session_state[k] = v

# Sidebar
st.sidebar.header("🎯 Metas de Qualidade")
st.sidebar.markdown(f"**📅 Mês: {mes_ref or 'N/D'}**")
st.sidebar.markdown("---")
st.sidebar.info("🔄 Dados atualizados automaticamente")

# Get product day
try: produto_dia_str = pd.to_datetime(df_dia.loc['PRODUTO_DIA', 'PMT 01']).strftime('%d/%m/%Y')
except: produto_dia_str = 'N/D'

# ========== RESULTADOS DO DIA ==========
st.subheader(f"📊 Resultados do Último Dia ({produto_dia_str})")

def render_metrics(df, pmt, title):
    st.markdown(f"### 🏭 {title}")
    with st.container():
        # Linha 1 - Fe, SiO2, Al2O3
        cols1 = st.columns(3)
        for col, (label, idx) in zip(cols1, [('Fe', 'Fe'), ('SiO₂', 'SiO2'), ('Al₂O₃', 'Al2O3')]):
            with col:
                val = df.loc[idx, pmt] if idx in df.index else None
                st.metric(label, fmt_pct(val))
        
        # Linha 2 - TMP, >31,5mm, <12mm
        cols2 = st.columns(3)
        for col, (label, idx, fmt_func) in zip(
            cols2,
            [('TMP', 'TMP', lambda x: fmt_med(x, 'mm')), 
             ('>31,5mm', '>31_5mm', fmt_pct), 
             ('<12mm', '<0_15mm', fmt_pct)]
        ):
            with col:
                val = df.loc[idx, pmt] if idx in df.index else None
                st.metric(label, fmt_func(val))

col1, col2 = st.columns(2)
with col1: render_metrics(df_dia, 'PMT 01', 'PMT 01 - TUPACERY')
with col2: render_metrics(df_dia, 'PMT 02', 'PMT 02 - TUPACERY')

st.markdown("---")

# ========== MÉDIA DO MÊS ==========
st.subheader("📈 Média Geral do Mês")
col1, col2 = st.columns(2)
with col1: render_metrics(df_media, 'PMT 01', 'PMT 01 - TUPACERY')
with col2: render_metrics(df_media, 'PMT 02', 'PMT 02 - TUPACERY')

st.markdown("---")

# ========== ANÁLISES ==========
st.subheader("📊 Distribuição e Consistência da Qualidade no Mês")

if isinstance(df_box, pd.DataFrame) and not df_box.empty:
    ind_sel = st.selectbox("🎯 Selecione um Indicador", INDICADORES)
    if ind_sel:
        df_box[ind_sel] = pd.to_numeric(df_box[ind_sel], errors='coerce')
        df_plot = df_box.dropna(subset=[ind_sel, 'Data'])[lambda x: x[ind_sel] != 0].copy()
        
        if not df_plot.empty:
            # Boxplot
            fig_box = px.box(df_plot, x='Peneira', y=ind_sel, color='Peneira', points=False, 
                           title=f"📊 Distribuição de {ind_sel} - {mes_ref}")
            fig_box.update_layout(template='plotly_white', height=500, showlegend=True)
            fig_box.update_yaxes(tickformat=',.2f', title=f"{ind_sel} ({'%' if ind_sel in ['Fe', 'SiO2', 'Al2O3', '>31_5mm', '<0_15mm'] else 'mm' if ind_sel == 'TMP' else ''})")
            st.plotly_chart(fig_box, use_container_width=True)
            
            # Stats
            col1, col2 = st.columns(2)
            for col, pmt in [(col1, 'PMT 01'), (col2, 'PMT 02')]:
                with col:
                    st.markdown(f"#### 📈 Estatísticas - {pmt}")
                    data = df_plot[df_plot['Peneira'] == pmt][ind_sel]
                    if not data.empty:
                        for stat, func in [('Média', 'mean'), ('Mediana', 'median'), ('Desvio Padrão', 'std'), ('Mínimo', 'min'), ('Máximo', 'max')]:
                            st.write(f"**{stat}:** {fmt_num(getattr(data, func)())}")
                    else: st.info("Sem dados válidos")

# ========== TENDÊNCIAS ==========
st.markdown("---")
st.subheader("📈 Análise de Tendências Temporais")

if isinstance(df_box, pd.DataFrame) and not df_box.empty:
    ind_trend = st.selectbox("📊 Indicador para Tendência", INDICADORES, key="trend")
    if ind_trend:
        df_trend = df_box.copy()
        df_trend[ind_trend] = pd.to_numeric(df_trend[ind_trend], errors='coerce')
        df_trend = df_trend.dropna(subset=[ind_trend, 'Data'])[lambda x: x[ind_trend] != 0]
        
        if not df_trend.empty:
            # Line chart
            fig_line = px.line(df_trend.sort_values('Data'), x='Data', y=ind_trend, color='Peneira', 
                             title=f"📈 Evolução de {ind_trend} - {mes_ref}", markers=True)
            fig_line.update_layout(template='plotly_white', height=400)
            fig_line.update_yaxes(tickformat=',.2f')
            st.plotly_chart(fig_line, use_container_width=True)
            
            # Variability
            st.markdown("#### 🎯 Análise de Variabilidade")
            col1, col2 = st.columns(2)
            for col, pmt in [(col1, 'PMT 01'), (col2, 'PMT 02')]:
                with col:
                    data = df_trend[df_trend['Peneira'] == pmt][ind_trend]
                    if not data.empty and data.mean() != 0:
                        cv = (data.std() / data.mean()) * 100
                        st.metric(f"Coef. Variação - {pmt}", fmt_pct(cv))
                    else: st.metric(f"Coef. Variação - {pmt}", "N/D")

# Footer
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666; font-size: 0.8em;'>Dashboard de Qualidade - LHG Mining | Tupacery</div>", unsafe_allow_html=True)