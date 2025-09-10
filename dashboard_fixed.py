import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta, datetime
import hashlib

# --- Funções de Utilitário ---
def get_last_update_info():
    """Lê informações da última atualização do arquivo JSON"""
    try:
        with open('last_update.json', 'r') as f:
            update_info = json.load(f)
        return update_info
    except:
        return {"timestamp": 0, "last_update": "Não disponível"}

# Função para carregar usuários do arquivo users.txt
def load_users():
    users = {}
    try:
        if os.path.exists("users.txt"):
            with open("users.txt", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split(":")
                        if len(parts) == 2:
                            username, password_hash = parts
                            users[username] = password_hash
        else:
            # Criar arquivo padrão se não existir
            default_users = [
                "# Arquivo de usuários - Formato: usuario:senha_hash",
                "# Para gerar hash de senha, use: echo -n \"sua_senha\" | sha256sum",
                "admin:5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
                "lhg_user:ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
                "expedicao:a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"
            ]
            with open("users.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(default_users))
            # Recarregar após criar o arquivo
            return load_users()
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {str(e)}")
    
    return users

# Função para hash da senha
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# Função para verificar login
def check_password(username, password):
    users = load_users()
    if username in users:
        return users[username] == hash_password(password)
    return False

# Função para registrar log de acesso em arquivo TXT
def log_access(username, action="login"):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | {username} | {action}\n"
        
        # Salvar no arquivo access_logs.txt
        with open("access_logs.txt", "a", encoding="utf-8") as f:
            f.write(log_entry)
            
    except Exception as e:
        st.error(f"Erro ao registrar log: {str(e)}")

# Função de login
def login_form():
    st.title("🔐 Login - Dashboard LHG Logística")
    st.markdown("---")
    
    # Informações de login para teste
    with st.expander("ℹ️ Credenciais de Teste"):
        st.write("**Usuários disponíveis:**")
        st.write("- **admin** / admin")
    
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button("Entrar")
        
        if submit_button:
            if check_password(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                log_access(username, "login")
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos!")
                log_access(username, "failed_login")

@st.cache_data
def load_and_preprocess_data(file_path, start_date, end_date, cache_key):
    try:
        df = pd.read_excel(file_path)

        # Renomear colunas para facilitar o uso
        df.rename(columns={
            'data de Inclusão': 'DataInclusao',
            'Quantidade': 'ConsumoDiesel',
            'Valo Unitário': 'CustoUnitario',
            'Valor Total': 'CustoTotalAbastecimento',
            'Área': 'Setor',
            'Dia': 'DataConsumo'
        }, inplace=True)

        # Converter as colunas de data para datetime
        df['DataInclusao'] = pd.to_datetime(df['DataInclusao'])
        df['DataConsumo'] = pd.to_datetime(df['DataConsumo'])

        # Filtrar apenas os setores 'Tup' e 'Rep'
        df = df[df['Setor'].isin(['Tup', 'Rep'])].copy()

        # Renomear 'Tup' para 'Expedição' e 'Rep' para 'Peneiramento'
        df['Setor'] = df['Setor'].replace({'Tup': 'Expedição', 'Rep': 'Peneiramento'})

        # Garantir que o consumo e custos são numéricos
        df['ConsumoDiesel'] = pd.to_numeric(df['ConsumoDiesel'], errors='coerce')
        df['CustoUnitario'] = pd.to_numeric(df['CustoUnitario'], errors='coerce')
        df['CustoTotalAbastecimento'] = pd.to_numeric(df['CustoTotalAbastecimento'], errors='coerce')
        df.dropna(subset=['ConsumoDiesel', 'CustoUnitario', 'CustoTotalAbastecimento'], inplace=True)

        # Aplicar filtro de data se fornecido
        if start_date and end_date:
            df = df[(df['DataConsumo'] >= pd.to_datetime(start_date)) & 
                   (df['DataConsumo'] <= pd.to_datetime(end_date))]

        # Calcular o consumo diário e custo diário por setor
        daily_data = df.groupby(['DataConsumo', 'Setor']).agg(
            ConsumoDiario=('ConsumoDiesel', 'sum'),
            CustoDiario=('CustoTotalAbastecimento', 'sum')
        ).reset_index()

        # Calcular o consumo acumulado e custo acumulado por setor
        daily_data = daily_data.sort_values(by=['DataConsumo', 'Setor'])
        daily_data['ConsumoAcumulado'] = daily_data.groupby('Setor')['ConsumoDiario'].cumsum()
        daily_data['CustoAcumulado'] = daily_data.groupby('Setor')['CustoDiario'].cumsum()

        return daily_data, df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()

# Função para calcular KPIs
def calculate_kpis(df, period_type="month"):
    if df.empty:
        return {}
    
    try:
        today = pd.to_datetime(date.today())
        
        # Ajustar cálculo baseado no tipo de período
        if period_type == "month":
            # Filtrar dados do mês atual, excluindo o dia atual para cálculo de tendência e projeção
            current_period_data_complete_days = df[(df['DataConsumo'].dt.month == today.month) & (df['DataConsumo'] < today)]
        else:
            # Para períodos personalizados, usar todos os dados exceto o último dia
            unique_dates = sorted(df['DataConsumo'].unique())
            if len(unique_dates) > 1:
                current_period_data_complete_days = df[df['DataConsumo'] < unique_dates[-1]]
            else:
                current_period_data_complete_days = df

        # Consumo acumulado do período
        total_consumed_expedicao = df[df['Setor'] == 'Expedição']['ConsumoDiario'].sum()
        total_consumed_peneiramento = df[df['Setor'] == 'Peneiramento']['ConsumoDiario'].sum()
        total_consumed_period = total_consumed_expedicao + total_consumed_peneiramento

        # Custo total acumulado do período
        total_cost_expedicao = df[df['Setor'] == 'Expedição']['CustoDiario'].sum()
        total_cost_peneiramento = df[df['Setor'] == 'Peneiramento']['CustoDiario'].sum()
        total_cost_period = total_cost_expedicao + total_cost_peneiramento

        # Custo médio do litro de diesel (total de custo / total de consumo)
        avg_liter_cost = total_cost_period / total_consumed_period if total_consumed_period > 0 else 0

        # Consumo médio diário (para projeção, baseado em dias completos)
        days_in_period_so_far = len(current_period_data_complete_days['DataConsumo'].unique())
        avg_daily_consumption = current_period_data_complete_days['ConsumoDiario'].sum() / days_in_period_so_far if days_in_period_so_far > 0 else 0
        
        # Custo médio diário (para projeção, baseado em dias completos)
        avg_daily_cost = current_period_data_complete_days['CustoDiario'].sum() / days_in_period_so_far if days_in_period_so_far > 0 else 0

        # Estimativa de fechamento (apenas para período mensal)
        if period_type == "month":
            last_day_of_month = (pd.Timestamp(today.year, today.month, 1) + pd.DateOffset(months=1) - pd.DateOffset(days=1)).day
            days_remaining_in_month = last_day_of_month - today.day
            projected_consumption = total_consumed_period + (avg_daily_consumption * days_remaining_in_month)
            projected_cost = total_cost_period + (avg_daily_cost * days_remaining_in_month)
        else:
            projected_consumption = total_consumed_period
            projected_cost = total_cost_period

        # Tendência do ritmo de abastecimento (baseado nos últimos 7 dias completos)
        trend_data = current_period_data_complete_days.sort_values('DataConsumo').tail(7)
        trend = 'Não há dados suficientes'
        if len(trend_data) >= 6:
            avg_last_3_days = trend_data['ConsumoDiario'].tail(3).mean()
            avg_prev_3_days = trend_data['ConsumoDiario'].iloc[-6:-3].mean()
            
            if avg_prev_3_days == 0:
                trend = 'Estável (sem consumo anterior para comparação)'
            elif avg_last_3_days > avg_prev_3_days * 1.05:
                trend = 'Aumentando'
            elif avg_last_3_days < avg_prev_3_days * 0.95:
                trend = 'Diminuindo'
            else:
                trend = 'Estável'
        elif len(current_period_data_complete_days['DataConsumo'].unique()) >= 2:
            unique_dates = sorted(current_period_data_complete_days['DataConsumo'].unique())
            last_day_consumption = current_period_data_complete_days[current_period_data_complete_days['DataConsumo'] == unique_dates[-1]]['ConsumoDiario'].sum()
            second_last_day_consumption = current_period_data_complete_days[current_period_data_complete_days['DataConsumo'] == unique_dates[-2]]['ConsumoDiario'].sum()
            if last_day_consumption > second_last_day_consumption:
                trend = 'Aumentando'
            elif last_day_consumption < second_last_day_consumption:
                trend = 'Diminuindo'
            else:
                trend = 'Estável'

        return {
            'total_consumed_period': total_consumed_period,
            'avg_daily_consumption': avg_daily_consumption,
            'projected_consumption': projected_consumption,
            'trend': trend,
            'total_consumed_expedicao': total_consumed_expedicao,
            'total_consumed_peneiramento': total_consumed_peneiramento,
            'total_cost_period': total_cost_period,
            'avg_daily_cost': avg_daily_cost,
            'projected_cost': projected_cost,
            'avg_liter_cost': avg_liter_cost
        }
    except Exception as e:
        st.error(f"Erro ao calcular KPIs: {str(e)}")
        return {}

# Função para gerar insights automáticos
def generate_insights(kpis, period_label="mês"):
    if not kpis:
        return ["Não foi possível gerar insights devido a problemas nos dados."]
    
    insights = []
    
    try:
        # Qual setor consome mais
        if kpis.get('total_consumed_expedicao', 0) > kpis.get('total_consumed_peneiramento', 0):
            insights.append(f"O setor Expedição consome mais diesel, com {format_number(kpis['total_consumed_expedicao'])} litros acumulados no {period_label}, comparado aos {format_number(kpis['total_consumed_peneiramento'])} litros do setor Peneiramento.")
        else:
            insights.append(f"O setor Peneiramento consome mais diesel, com {format_number(kpis['total_consumed_peneiramento'])} litros acumulados no {period_label}, comparado aos {format_number(kpis['total_consumed_expedicao'])} litros do setor Expedição.")
        
        # Ritmo atual de consumo
        insights.append(f"O ritmo atual de abastecimento está {kpis['trend'].lower()}, com uma média diária de {format_number(kpis['avg_daily_consumption'])} litros e um custo médio diário de R$ {format_number(kpis['avg_daily_cost'])}.")
        
        # Projeção de fechamento
        if period_label == "mês":
            insights.append(f"Com base no consumo atual, a projeção para o fechamento do {period_label} é de {format_number(kpis['projected_consumption'])} litros de diesel, com um custo total estimado de R$ {format_number(kpis['projected_cost'])}.")
        else:
            insights.append(f"No período selecionado, o consumo total foi de {format_number(kpis['total_consumed_period'])} litros de diesel, com um custo total de R$ {format_number(kpis['total_cost_period'])}.")
        
    except Exception as e:
        insights.append(f"Erro ao gerar insights: {str(e)}")
    
    return insights

# Função para formatar números com ponto como separador de milhar e sem decimais
def format_number(value):
    return f"{int(value):,}".replace(",", ".")

# Função para criar histograma de consumo por equipamento
def create_equipment_histogram(df_original):
    if df_original.empty or 'Tag' not in df_original.columns:
        return None, None
    
    try:
        # Agrupar por Tag e Setor para obter o consumo total por equipamento
        equipment_data = df_original.groupby(['Tag', 'Setor'])['ConsumoDiesel'].sum().reset_index()
        
        # Separar por setor
        expedicao_data = equipment_data[equipment_data['Setor'] == 'Expedição'].sort_values('ConsumoDiesel', ascending=True)
        peneiramento_data = equipment_data[equipment_data['Setor'] == 'Peneiramento'].sort_values('ConsumoDiesel', ascending=True)
        
        # Criar gráfico para Expedição
        fig_expedicao = None
        if not expedicao_data.empty:
            fig_expedicao = px.bar(
                expedicao_data,
                x='ConsumoDiesel',
                y='Tag',
                orientation='h',
                title="Consumo por Equipamento - Expedição",
                labels={'ConsumoDiesel': 'Consumo (Litros)', 'Tag': 'Equipamento'},
                color_discrete_sequence=["#FF6600"]
            )
            fig_expedicao.update_layout(height=400, showlegend=False)
            fig_expedicao.update_traces(
                texttemplate='%{x:,.0f}L',
                textposition='outside'
            )
        
        # Criar gráfico para Peneiramento
        fig_peneiramento = None
        if not peneiramento_data.empty:
            fig_peneiramento = px.bar(
                peneiramento_data,
                x='ConsumoDiesel',
                y='Tag',
                orientation='h',
                title="Consumo por Equipamento - Peneiramento",
                labels={'ConsumoDiesel': 'Consumo (Litros)', 'Tag': 'Equipamento'},
                color_discrete_sequence=["#808080"]
            )
            fig_peneiramento.update_layout(height=400, showlegend=False)
            fig_peneiramento.update_traces(
                texttemplate='%{x:,.0f}L',
                textposition='outside'
            )
        
        return fig_expedicao, fig_peneiramento
        
    except Exception as e:
        st.error(f"Erro ao criar histograma de equipamentos: {str(e)}")
        return None, None

# --- Configuração da Página ---
st.set_page_config(
    page_title="Dashboard de Consumo de Diesel - LHG Logística",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded"
)

PRIMARY_COLOR = "#FF6600"
SECONDARY_COLOR = "#808080"

# --- Interface Principal ---
def main():
    # Verificar autenticação
    if not st.session_state.get('authenticated', False):
        login_form()
        return
    
    # Pega informações da última atualização
    update_info = get_last_update_info()
    
    # Cabeçalho com logo e título
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if os.path.exists("Lhg-02.png"):
            st.image("Lhg-02.png", width=150)
        else:
            st.write("🏢 LHG")
    with col2:
        st.title("Dashboard de Consumo de Diesel")
        st.subheader("LHG Logística - Expedição (Expedição e Peneiramento)")
    with col3:
        if st.button("🚪 Logout"):
            log_access(st.session_state.username, "logout")
            st.session_state.authenticated = False
            st.session_state.username = None
            st.rerun()

    # Sidebar para configurações
    st.sidebar.header("📋 Configurações")
    st.sidebar.info(f"Usuário: {st.session_state.get('username', 'Desconhecido')}")
    st.sidebar.info(f"🔄 Última atualização: {update_info.get('last_update', 'N/A')[:19]}")

    # Filtros de data na sidebar
    st.sidebar.header("📅 Filtros de Data")
    
    filter_type = st.sidebar.selectbox(
        "Tipo de Filtro",
        ["Mês Atual", "Período Personalizado", "Mês Específico"]
    )
    
    start_date = None
    end_date = None
    period_label = "mês"
    period_type = "month"
    
    if filter_type == "Período Personalizado":
        start_date = st.sidebar.date_input("Data Inicial", value=date.today() - timedelta(days=30))
        end_date = st.sidebar.date_input("Data Final", value=date.today())
        period_label = f"período de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
        period_type = "custom"
    elif filter_type == "Mês Específico":
        selected_month = st.sidebar.selectbox("Selecione o Mês", 
                                            ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                                             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])
        selected_year = st.sidebar.selectbox("Selecione o Ano", [datetime.now().year, datetime.now().year - 1, datetime.now().year - 2])
        
        month_num = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                     "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"].index(selected_month) + 1
        
        start_date = date(selected_year, month_num, 1)
        if month_num == 12:
            end_date = date(selected_year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(selected_year, month_num + 1, 1) - timedelta(days=1)
        
        period_label = f"{selected_month} de {selected_year}"
        period_type = "custom"
    
    file_path = "Diesel-area.xlsx"
    
    if not os.path.exists(file_path):
        st.error("Arquivo de dados não encontrado! Certifique-se de que 'Diesel-area.xlsx' está na mesma pasta que o script.")
        return

    # Usar o timestamp do JSON como cache_key
    cache_key = update_info.get('timestamp', 0)
    
    with st.spinner("Carregando dados..."):
        df, df_original = load_and_preprocess_data(file_path, start_date, end_date, cache_key=cache_key)
        
    if df.empty:
        st.error("Não foi possível carregar os dados ou não há dados válidos para o período selecionado.")
        return
        
    kpis = calculate_kpis(df, period_type)
    insights = generate_insights(kpis, period_label)
    
    if not kpis:
        st.error("Não foi possível calcular os KPIs. Verifique os dados de entrada.")
        return
    
    # Estilo CSS personalizado para cores da logo
    st.markdown(f"""
    <style>
    .stMetric {{ background-color: #f0f2f6; border-radius: 10px; padding: 15px; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }}
    .stMetric label {{ color: {SECONDARY_COLOR}; font-weight: bold; }}
    .stMetric div[data-testid="stMetricValue"] {{ color: {PRIMARY_COLOR}; font-size: 2.5em; }}
    .stPlotlyChart {{ border-radius: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); padding: 10px; background-color: white; }}
    </style>
    """, unsafe_allow_html=True)

    # KPI Cards
    st.header("📊 Indicadores Principais")
    
    # Primeira linha de KPIs (Consumo)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label=f"Consumo Acumulado ({period_label.title()})",
            value=f"{format_number(kpis['total_consumed_period'])} L"
        )
    with col2:
        st.metric(
            label="Consumo Médio Diário",
            value=f"{format_number(kpis['avg_daily_consumption'])} L"
        )
    with col3:
        if period_type == "month":
            st.metric(
                label="Projeção Consumo Fechamento",
                value=f"{format_number(kpis['projected_consumption'])} L"
            )
        else:
            st.metric(
                label="Total do Período",
                value=f"{format_number(kpis['total_consumed_period'])} L"
            )
    
    # Segunda linha de KPIs (Custo)
    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric(
            label=f"Custo Total Acumulado ({period_label.title()})",
            value=f"R$ {format_number(kpis['total_cost_period'])}"
        )
    with col5:
        st.metric(
            label="Custo Médio Diário",
            value=f"R$ {format_number(kpis['avg_daily_cost'])}"
        )
    with col6:
        if period_type == "month":
            st.metric(
                label="Projeção Custo Fechamento",
                value=f"R$ {format_number(kpis['projected_cost'])}"
            )
        else:
            st.metric(
                label="Custo Total do Período",
                value=f"R$ {format_number(kpis['total_cost_period'])}"
            )
    
    # Terceira linha de KPIs (Custo por Litro e Tendência)
    col7, col8 = st.columns(2)
    with col7:
        st.metric(
            label="Custo Médio Litro Diesel",
            value=f"R$ {kpis['avg_liter_cost']:.2f}"
        )
    with col8:
        st.metric(
            label="Tendência de Consumo",
            value=kpis['trend']
        )

    # Gráficos
    st.header("📈 Visualizações")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de linha - Evolução diária do consumo
        st.subheader("Evolução Diária do Consumo")
        if not df.empty:
            fig_line_consumo = px.line(
                df, 
                x='DataConsumo', 
                y='ConsumoDiario', 
                color='Setor',
                title="Consumo Diário por Setor",
                labels={'DataConsumo': 'Data', 'ConsumoDiario': 'Consumo (Litros)', 'Setor': 'Setor'},
                color_discrete_map={'Expedição': PRIMARY_COLOR, 'Peneiramento': SECONDARY_COLOR}
            )
            fig_line_consumo.update_layout(height=400)
            st.plotly_chart(fig_line_consumo, use_container_width=True)
        else:
            st.warning("Não há dados para exibir o gráfico de evolução diária de consumo.")
    
    with col2:
        # Gráfico de barras - Comparação acumulada de consumo
        st.subheader("Comparação Acumulada de Consumo")
        if kpis:
            comparison_data_consumo = pd.DataFrame({
                'Setor': ['Expedição', 'Peneiramento'],
                'Consumo Acumulado': [kpis.get('total_consumed_expedicao', 0), kpis.get('total_consumed_peneiramento', 0)]
            })
            
            fig_bar_consumo = px.bar(
                comparison_data_consumo,
                x='Setor',
                y='Consumo Acumulado',
                title="Consumo Acumulado por Setor",
                labels={'Consumo Acumulado': 'Consumo (Litros)'},
                color='Setor',
                color_discrete_map={'Expedição': PRIMARY_COLOR, 'Peneiramento': SECONDARY_COLOR}
            )
            fig_bar_consumo.update_layout(height=400)
            st.plotly_chart(fig_bar_consumo, use_container_width=True)
        else:
            st.warning("Não há dados para exibir o gráfico de comparação de consumo.")

    # Histogramas de consumo por equipamento
    st.header("🚛 Consumo por Equipamento")
    
    if not df_original.empty:
        fig_exp, fig_pen = create_equipment_histogram(df_original)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if fig_exp:
                st.plotly_chart(fig_exp, use_container_width=True)
            else:
                st.warning("Não há dados de equipamentos para Expedição no período selecionado.")
        
        with col2:
            if fig_pen:
                st.plotly_chart(fig_pen, use_container_width=True)
            else:
                st.warning("Não há dados de equipamentos para Peneiramento no período selecionado.")
    else:
        st.warning("Não há dados para exibir o consumo por equipamento.")

    # Insights automáticos
    st.header("🔍 Insights Automáticos")
    for i, insight in enumerate(insights, 1):
        st.write(f"**{i}.** {insight}")

    # Tabela de dados
    st.header("📋 Dados Detalhados")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Não há dados para exibir.")
        
    # Informações adicionais na sidebar
    st.sidebar.header("ℹ️ Informações")
    st.sidebar.info(f"Total de registros: {len(df)}")
    if not df.empty:
        st.sidebar.info(f"Período: {df['DataConsumo'].min().strftime('%d/%m/%Y')} a {df['DataConsumo'].max().strftime('%d/%m/%Y')}")

    # Adiciona botão na sidebar para forçar refresh manual e clear cache
    if st.sidebar.button("🔄 Forçar Atualização"):
        st.cache_data.clear()
        st.rerun()

if __name__ == "__main__":
    main()