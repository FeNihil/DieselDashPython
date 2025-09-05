
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import os

# Configuração da página
st.set_page_config(
    page_title="Dashboard de Consumo de Diesel - LHG Logística",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cores da logo para estilização (laranja e cinza)
PRIMARY_COLOR = "#FF6600"  # Laranja da logo
SECONDARY_COLOR = "#808080" # Cinza da logo

# Função para carregar e processar os dados
@st.cache_data(ttl=3600) # Cache por 1 hora
def load_and_preprocess_data(file_path):
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

        # Calcular o consumo diário e custo diário por setor
        daily_data = df.groupby(['DataConsumo', 'Setor']).agg(
            ConsumoDiario=('ConsumoDiesel', 'sum'),
            CustoDiario=('CustoTotalAbastecimento', 'sum')
        ).reset_index()

        # Calcular o consumo acumulado e custo acumulado por setor
        daily_data = daily_data.sort_values(by=['DataConsumo', 'Setor'])
        daily_data['ConsumoAcumulado'] = daily_data.groupby('Setor')['ConsumoDiario'].cumsum()
        daily_data['CustoAcumulado'] = daily_data.groupby('Setor')['CustoDiario'].cumsum()

        return daily_data
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

# Função para calcular KPIs
def calculate_kpis(df):
    if df.empty:
        return {}
    
    try:
        today = pd.to_datetime(date.today())
        
        # Filtrar dados do mês atual, excluindo o dia atual para cálculo de tendência e projeção
        current_month_data_complete_days = df[(df['DataConsumo'].dt.month == today.month) & (df['DataConsumo'] < today)]

        # Consumo acumulado do mês até hoje (considerando todos os dados disponíveis, incluindo o dia atual)
        total_consumed_expedicao = df[df['Setor'] == 'Expedição']['ConsumoDiario'].sum()
        total_consumed_peneiramento = df[df['Setor'] == 'Peneiramento']['ConsumoDiario'].sum()
        total_consumed_month = total_consumed_expedicao + total_consumed_peneiramento

        # Custo total acumulado do mês até hoje
        total_cost_expedicao = df[df['Setor'] == 'Expedição']['CustoDiario'].sum()
        total_cost_peneiramento = df[df['Setor'] == 'Peneiramento']['CustoDiario'].sum()
        total_cost_month = total_cost_expedicao + total_cost_peneiramento

        # Custo médio do litro de diesel (total de custo / total de consumo)
        avg_liter_cost = total_cost_month / total_consumed_month if total_consumed_month > 0 else 0

        # Consumo médio diário (para projeção, baseado em dias completos)
        days_in_month_so_far = len(current_month_data_complete_days['DataConsumo'].unique())
        avg_daily_consumption = current_month_data_complete_days['ConsumoDiario'].sum() / days_in_month_so_far if days_in_month_so_far > 0 else 0
        
        # Custo médio diário (para projeção, baseado em dias completos)
        avg_daily_cost = current_month_data_complete_days['CustoDiario'].sum() / days_in_month_so_far if days_in_month_so_far > 0 else 0

        # Estimativa de fechamento do mês
        last_day_of_month = (pd.Timestamp(today.year, today.month, 1) + pd.DateOffset(months=1) - pd.DateOffset(days=1)).day
        days_remaining_in_month = last_day_of_month - today.day
        
        projected_consumption = total_consumed_month + (avg_daily_consumption * days_remaining_in_month)
        projected_cost = total_cost_month + (avg_daily_cost * days_remaining_in_month)

        # Tendência do ritmo de abastecimento (baseado nos últimos 7 dias completos)
        trend_data = current_month_data_complete_days.sort_values('DataConsumo').tail(7)
        trend = 'Não há dados suficientes'
        if len(trend_data) >= 6: # Precisamos de pelo menos 6 dias para comparar 3 dias com os 3 anteriores
            avg_last_3_days = trend_data['ConsumoDiario'].tail(3).mean()
            avg_prev_3_days = trend_data['ConsumoDiario'].iloc[-6:-3].mean()
            
            if avg_prev_3_days == 0: # Evitar divisão por zero
                trend = 'Estável (sem consumo anterior para comparação)'
            elif avg_last_3_days > avg_prev_3_days * 1.05: # Aumento de 5%
                trend = 'Aumentando'
            elif avg_last_3_days < avg_prev_3_days * 0.95: # Diminuição de 5%
                trend = 'Diminuindo'
            else:
                trend = 'Estável'
        elif len(current_month_data_complete_days['DataConsumo'].unique()) >= 2: # Se tiver pelo menos 2 dias completos
            unique_dates = sorted(current_month_data_complete_days['DataConsumo'].unique())
            last_day_consumption = current_month_data_complete_days[current_month_data_complete_days['DataConsumo'] == unique_dates[-1]]['ConsumoDiario'].sum()
            second_last_day_consumption = current_month_data_complete_days[current_month_data_complete_days['DataConsumo'] == unique_dates[-2]]['ConsumoDiario'].sum()
            if last_day_consumption > second_last_day_consumption:
                trend = 'Aumentando'
            elif last_day_consumption < second_last_day_consumption:
                trend = 'Diminuindo'
            else:
                trend = 'Estável'

        return {
            'total_consumed_month': total_consumed_month,
            'avg_daily_consumption': avg_daily_consumption,
            'projected_consumption': projected_consumption,
            'trend': trend,
            'total_consumed_expedicao': total_consumed_expedicao,
            'total_consumed_peneiramento': total_consumed_peneiramento,
            'total_cost_month': total_cost_month,
            'avg_daily_cost': avg_daily_cost,
            'projected_cost': projected_cost,
            'avg_liter_cost': avg_liter_cost
        }
    except Exception as e:
        st.error(f"Erro ao calcular KPIs: {str(e)}")
        return {}

# Função para gerar insights automáticos
def generate_insights(kpis):
    if not kpis:
        return ["Não foi possível gerar insights devido a problemas nos dados."]
    
    insights = []
    
    try:
        # Qual setor consome mais
        if kpis.get('total_consumed_expedicao', 0) > kpis.get('total_consumed_peneiramento', 0):
            insights.append(f"O setor Expedição consome mais diesel, com {format_number(kpis['total_consumed_expedicao'])} litros acumulados no mês, comparado aos {format_number(kpis['total_consumed_peneiramento'])} litros do setor Peneiramento.")
        else:
            insights.append(f"O setor Peneiramento consome mais diesel, com {format_number(kpis['total_consumed_peneiramento'])} litros acumulados no mês, comparado aos {format_number(kpis['total_consumed_expedicao'])} litros do setor Expedição.")
        
        # Ritmo atual de consumo
        insights.append(f"O ritmo atual de abastecimento está {kpis['trend'].lower()}, com uma média diária de {format_number(kpis['avg_daily_consumption'])} litros e um custo médio diário de R$ {format_number(kpis['avg_daily_cost'])}.")
        
        # Projeção de fechamento
        insights.append(f"Com base no consumo atual, a projeção para o fechamento do mês é de {format_number(kpis['projected_consumption'])} litros de diesel, com um custo total estimado de R$ {format_number(kpis['projected_cost'])}.")
        
    except Exception as e:
        insights.append(f"Erro ao gerar insights: {str(e)}")
    
    return insights

# Função para formatar números com ponto como separador de milhar e sem decimais
def format_number(value):
    return f"{int(value):,}".replace(",", ".")

# Interface principal
def main():
    # Cabeçalho com logo e título
    col1, col2 = st.columns([1, 4])
    with col1:
        st.image("Lhg-02.png", width=150) # Caminho relativo para a logo
    with col2:
        st.title("Dashboard de Consumo de Diesel")
        st.subheader("LHG Logística - Expedição (Expedição e Peneiramento)")

    # Sidebar para configurações
    st.sidebar.header("📋 Configurações")
    
    # Usar arquivo padrão (assumindo que está na mesma pasta)
    file_path = "Diesel-area.xlsx"
    
    if not os.path.exists(file_path):
        st.error("Arquivo de dados não encontrado! Certifique-se de que 'Diesel-area.xlsx' está na mesma pasta que o script.")
        return

    # Carregar e processar dados
    with st.spinner("Carregando dados..."):
        df = load_and_preprocess_data(file_path)
        
    if df.empty:
        st.error("Não foi possível carregar os dados ou não há dados válidos após o processamento.")
        return
        
    kpis = calculate_kpis(df)
    insights = generate_insights(kpis)
    
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
            label="Consumo Acumulado (Mês)",
            value=f"{format_number(kpis['total_consumed_month'])} L"
        )
    with col2:
        st.metric(
            label="Consumo Médio Diário",
            value=f"{format_number(kpis['avg_daily_consumption'])} L"
        )
    with col3:
        st.metric(
            label="Projeção Consumo Fechamento",
            value=f"{format_number(kpis['projected_consumption'])} L"
        )
    
    # Segunda linha de KPIs (Custo)
    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric(
            label="Custo Total Acumulado (Mês)",
            value=f"R$ {format_number(kpis['total_cost_month'])}"
        )
    with col5:
        st.metric(
            label="Custo Médio Diário",
            value=f"R$ {format_number(kpis['avg_daily_cost'])}"
        )
    with col6:
        st.metric(
            label="Projeção Custo Fechamento",
            value=f"R$ {format_number(kpis['projected_cost'])}"
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

if __name__ == "__main__":
    main()


