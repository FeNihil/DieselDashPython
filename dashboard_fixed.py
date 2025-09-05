import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
import os

# Configuração da página
st.set_page_config(
    page_title="Dashboard de Consumo de Diesel - LHG Logística",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Função para carregar e processar os dados
@st.cache_data
def load_and_preprocess_data(file_path):
    try:
        df = pd.read_excel(file_path)

        # Renomear colunas para facilitar o uso
        df.rename(columns={
            'data de Inclusão': 'DataInclusao',
            'Quantidade': 'ConsumoDiesel',
            'Área': 'Setor',
            'Dia': 'DataConsumo'
        }, inplace=True)

        # Converter as colunas de data para datetime
        df['DataInclusao'] = pd.to_datetime(df['DataInclusao'])
        df['DataConsumo'] = pd.to_datetime(df['DataConsumo'])

        # Filtrar apenas os setores 'Tup' e 'Rep'
        df = df[df['Setor'].isin(['Tup', 'Rep'])].copy()

        # Garantir que o consumo é numérico
        df['ConsumoDiesel'] = pd.to_numeric(df['ConsumoDiesel'], errors='coerce')
        df.dropna(subset=['ConsumoDiesel'], inplace=True)

        # Calcular o consumo diário por setor
        daily_consumption = df.groupby(['DataConsumo', 'Setor'])['ConsumoDiesel'].sum().reset_index()
        daily_consumption.rename(columns={'ConsumoDiesel': 'ConsumoDiario'}, inplace=True)

        # Calcular o consumo acumulado por setor
        daily_consumption = daily_consumption.sort_values(by=['DataConsumo', 'Setor'])
        daily_consumption['ConsumoAcumulado'] = daily_consumption.groupby('Setor')['ConsumoDiario'].cumsum()

        return daily_consumption
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

# Função para calcular KPIs
def calculate_kpis(df):
    if df.empty:
        return {}
    
    try:
        today = pd.to_datetime(date.today())
        current_month_data = df[df['DataConsumo'].dt.month == today.month]

        # Consumo acumulado do mês até hoje
        total_consumed_tup = current_month_data[current_month_data['Setor'] == 'Tup']['ConsumoDiario'].sum()
        total_consumed_rep = current_month_data[current_month_data['Setor'] == 'Rep']['ConsumoDiario'].sum()
        total_consumed_month = total_consumed_tup + total_consumed_rep

        # Consumo médio diário
        days_in_month_so_far = len(current_month_data['DataConsumo'].unique())
        avg_daily_consumption = total_consumed_month / days_in_month_so_far if days_in_month_so_far > 0 else 0

        # Estimativa de fechamento do mês
        days_remaining_in_month = (pd.Timestamp(today.year, today.month, 1) + pd.DateOffset(months=1) - pd.DateOffset(days=1)).day - today.day
        projected_consumption = total_consumed_month + (avg_daily_consumption * days_remaining_in_month)

        # Tendência do ritmo de abastecimento
        if days_in_month_so_far >= 2:
            unique_dates = sorted(current_month_data['DataConsumo'].unique())
            last_day_consumption = current_month_data[current_month_data['DataConsumo'] == unique_dates[-1]]['ConsumoDiario'].sum()
            second_last_day_consumption = current_month_data[current_month_data['DataConsumo'] == unique_dates[-2]]['ConsumoDiario'].sum()
            if last_day_consumption > second_last_day_consumption:
                trend = 'Aumentando'
            elif last_day_consumption < second_last_day_consumption:
                trend = 'Diminuindo'
            else:
                trend = 'Estável'
        else:
            trend = 'Não há dados suficientes'

        return {
            'total_consumed_month': total_consumed_month,
            'avg_daily_consumption': avg_daily_consumption,
            'projected_consumption': projected_consumption,
            'trend': trend,
            'total_consumed_tup': total_consumed_tup,
            'total_consumed_rep': total_consumed_rep
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
        if kpis['total_consumed_tup'] > kpis['total_consumed_rep']:
            insights.append(f"O setor TUP (Tupacery) consome mais diesel, com {kpis['total_consumed_tup']:.0f} litros acumulados no mês, comparado aos {kpis['total_consumed_rep']:.0f} litros do setor REP (Peneiramento).")
        else:
            insights.append(f"O setor REP (Peneiramento) consome mais diesel, com {kpis['total_consumed_rep']:.0f} litros acumulados no mês, comparado aos {kpis['total_consumed_tup']:.0f} litros do setor TUP (Tupacery).")
        
        # Ritmo atual de consumo
        insights.append(f"O ritmo atual de abastecimento está {kpis['trend'].lower()}, com uma média diária de {kpis['avg_daily_consumption']:.0f} litros.")
        
        # Projeção de fechamento
        insights.append(f"Com base no consumo atual, a projeção para o fechamento do mês é de {kpis['projected_consumption']:.0f} litros de diesel.")
        
    except Exception as e:
        insights.append(f"Erro ao gerar insights: {str(e)}")
    
    return insights

# Interface principal
def main():
    # Cabeçalho
    st.title("⛽ Dashboard de Consumo de Diesel")
    st.subheader("LHG Logística - Expedição (Setores TUP e REP)")

    # Sidebar para configurações
    st.sidebar.header("📋 Configurações")
    
    # Usar arquivo padrão
    file_path = "Diesel-area.xlsx"
    
    if not os.path.exists(file_path):
        st.error("Arquivo de dados não encontrado!")
        return

    # Carregar e processar dados
    with st.spinner("Carregando dados..."):
        df = load_and_preprocess_data(file_path)
        
    if df.empty:
        st.error("Não foi possível carregar os dados ou não há dados válidos.")
        return
        
    kpis = calculate_kpis(df)
    insights = generate_insights(kpis)
    
    if not kpis:
        st.error("Não foi possível calcular os KPIs.")
        return
    
    # KPI Cards
    st.header("📊 Indicadores Principais")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Consumo Acumulado (Mês)",
            value=f"{kpis['total_consumed_month']:.0f} L"
        )
    
    with col2:
        st.metric(
            label="Consumo Médio Diário",
            value=f"{kpis['avg_daily_consumption']:.0f} L"
        )
    
    with col3:
        st.metric(
            label="Projeção Fechamento",
            value=f"{kpis['projected_consumption']:.0f} L"
        )
    
    with col4:
        st.metric(
            label="Tendência",
            value=kpis['trend']
        )

    # Gráficos
    st.header("📈 Visualizações")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de linha - Evolução diária
        st.subheader("Evolução Diária do Consumo")
        if not df.empty:
            fig_line = px.line(
                df, 
                x='DataConsumo', 
                y='ConsumoDiario', 
                color='Setor',
                title="Consumo Diário por Setor",
                labels={'DataConsumo': 'Data', 'ConsumoDiario': 'Consumo (Litros)', 'Setor': 'Setor'}
            )
            fig_line.update_layout(height=400)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.warning("Não há dados para exibir o gráfico de evolução diária.")
    
    with col2:
        # Gráfico de barras - Comparação acumulada
        st.subheader("Comparação Acumulada")
        if kpis:
            comparison_data = pd.DataFrame({
                'Setor': ['TUP', 'REP'],
                'Consumo Acumulado': [kpis['total_consumed_tup'], kpis['total_consumed_rep']]
            })
            
            fig_bar = px.bar(
                comparison_data,
                x='Setor',
                y='Consumo Acumulado',
                title="Consumo Acumulado por Setor",
                labels={'Consumo Acumulado': 'Consumo (Litros)'},
                color='Setor'
            )
            fig_bar.update_layout(height=400)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("Não há dados para exibir o gráfico de comparação.")

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

