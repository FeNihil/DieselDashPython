import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta, datetime
import hashlib
import base64
from cryptography.fernet import Fernet
import io
import time

ENCRYPTED_FILENAME = "Diesel-area.encrypted"
ENCRYPTED_USERS_FILE = "users.encrypted"
ADMIN_USERNAME = "admin"  # Usuário administrador fixo

# --- Chave de Criptografia (Ofuscada) ---
# Busca da chave HEX salva nos segredos do Streamlit
HEX_KEY_STRING = st.secrets["HEX_KEY_STRING"]

fernet = None
if HEX_KEY_STRING:
    try:
        # Converte a string hexadecimal em bytes
        key_bytes = bytes.fromhex(HEX_KEY_STRING)
        # Codifica os bytes em base64 URL-safe, formato exigido pelo Fernet
        ENCRYPTION_KEY = base64.urlsafe_b64encode(key_bytes)
        fernet = Fernet(ENCRYPTION_KEY)
    except ValueError as e:
        st.error(f"❌ Erro na chave de criptografia. Verifique se a string hexadecimal está correta: {e}")
else:
    st.error("❌ Chave de criptografia não encontrada nos segredos do Streamlit!")

def decrypt_file_in_memory(file_path):
    """
    Lê um arquivo criptografado, descriptografa-o e retorna um objeto BytesIO.
    Isso permite que o pandas leia o arquivo sem salvá-lo no disco.
    """
    if not fernet:
        return None

    try:
        with open(file_path, "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()
        decrypted_data = fernet.decrypt(encrypted_data)
        # Retorna um objeto de arquivo em memória
        return io.BytesIO(decrypted_data)

    except FileNotFoundError:
        st.error(f"❌ Arquivo '{file_path}' não encontrado. Verifique se o arquivo existe.")
        return None
    except Exception as e:
        st.error(f"❌ Erro ao descriptografar o arquivo: {e}")
        return None

# --- Funções de Criptografia para Usuários ---
def encrypt_users_file(users_data):
    """Criptografa e salva os dados dos usuários"""
    if not fernet:
        return False
    
    try:
        # Converte o dicionário para JSON
        json_data = json.dumps(users_data, indent=2, ensure_ascii=False)
        # Converte para bytes
        data_bytes = json_data.encode('utf-8')
        # Criptografa
        encrypted_data = fernet.encrypt(data_bytes)
        
        # Salva no arquivo criptografado
        with open(ENCRYPTED_USERS_FILE, 'wb') as f:
            f.write(encrypted_data)
        
        return True
    except Exception as e:
        st.error(f"Erro ao criptografar arquivo de usuários: {str(e)}")
        return False

def decrypt_users_file():
    """Descriptografa e carrega os dados dos usuários"""
    if not fernet:
        return {}
    
    try:
        if not os.path.exists(ENCRYPTED_USERS_FILE):
            return {}
        
        with open(ENCRYPTED_USERS_FILE, 'rb') as f:
            encrypted_data = f.read()
        
        # Descriptografa
        decrypted_data = fernet.decrypt(encrypted_data)
        # Converte de volta para JSON
        json_data = decrypted_data.decode('utf-8')
        users = json.loads(json_data)
        
        return users
    except FileNotFoundError:
        return {}
    except Exception as e:
        st.error(f"Erro ao descriptografar arquivo de usuários: {str(e)}")
        return {}

# --- Funções de Utilitário ---
def get_last_update_info():
    """Lê informações da última atualização do arquivo JSON"""
    try:
        with open('last_update.json', 'r') as f:
            update_info = json.load(f)
        return update_info
    except:
        return {"timestamp": 0, "last_update": "Não disponível"}

# --- Funções de Gerenciamento de Usuários ---
def load_users():
    """Carrega usuários do arquivo criptografado"""
    return decrypt_users_file()

def save_users(users):
    """Salva usuários no arquivo criptografado"""
    return encrypt_users_file(users)

def hash_password(password):
    """Hash da senha usando SHA256"""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password(username, password):
    """Verifica login do usuário"""
    users = load_users()
    if username in users:
        return users[username]["password"] == hash_password(password)
    return False

def is_admin(username):
    """Verifica se o usuário é administrador"""
    users = load_users()
    return username in users and users[username].get("role") == "admin"

def create_user(username, password, email, full_name, role="user"):
    """Cria um novo usuário"""
    users = load_users()
    if username in users:
        return False, "Usuário já existe"
    
    users[username] = {
        "password": hash_password(password),
        "role": role,
        "email": email,
        "full_name": full_name,
        "created_at": datetime.now().isoformat(),
        "last_login": None
    }
    
    if save_users(users):
        return True, "Usuário criado com sucesso"
    else:
        return False, "Erro ao salvar usuário"

def update_user(username, email=None, full_name=None, role=None, new_password=None):
    """Atualiza informações do usuário"""
    users = load_users()
    if username not in users:
        return False, "Usuário não encontrado"
    
    if email:
        users[username]["email"] = email
    if full_name:
        users[username]["full_name"] = full_name
    if role:
        users[username]["role"] = role
    if new_password:
        users[username]["password"] = hash_password(new_password)
    
    if save_users(users):
        return True, "Usuário atualizado com sucesso"
    else:
        return False, "Erro ao salvar alterações"

def delete_user(username):
    """Remove usuário (não pode remover admin ou usuário atual)"""
    if username == ADMIN_USERNAME:
        return False, "Não é possível remover o usuário administrador"
    
    current_user = st.session_state.get('username')
    if username == current_user:
        return False, "Não é possível remover seu próprio usuário"
    
    users = load_users()
    if username not in users:
        return False, "Usuário não encontrado"
    
    del users[username]
    
    if save_users(users):
        return True, "Usuário removido com sucesso"
    else:
        return False, "Erro ao remover usuário"

def change_password(username, old_password, new_password):
    """Permite que o usuário altere sua própria senha"""
    users = load_users()
    if username not in users:
        return False, "Usuário não encontrado"
    
    if users[username]["password"] != hash_password(old_password):
        return False, "Senha atual incorreta"
    
    users[username]["password"] = hash_password(new_password)
    
    if save_users(users):
        return True, "Senha alterada com sucesso"
    else:
        return False, "Erro ao alterar senha"

def update_last_login(username):
    """Atualiza o timestamp do último login"""
    users = load_users()
    if username in users:
        users[username]["last_login"] = datetime.now().isoformat()
        save_users(users)

def log_access(username, action="login"):
    """Registra log de acesso em arquivo TXT"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | {username} | {action}\n"
        
        with open("access_logs.txt", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        st.error(f"Erro ao registrar log: {str(e)}")

# --- Interface de Login ---
def login_form():
    st.title("🔐 Login - Dashboard LHG Logística")
    st.markdown("---")
    
    # Opções de acesso
    access_mode = st.radio(
        "Selecione o modo de acesso:",
        ["Login Normal", "Painel de Usuários", "Alterar Senha"],
        horizontal=True
    )
    
    if access_mode == "Login Normal":
        normal_login()
    elif access_mode == "Painel de Usuários":
        admin_login()
    else:
        password_change_form()

def normal_login():
    """Formulário de login normal"""
    st.subheader("Acesso ao Dashboard")
    
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button("Entrar")
        
        if submit_button:
            if username and password:
                if check_password(username, password):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.is_admin = is_admin(username)
                    st.session_state.access_mode = "dashboard"
                    update_last_login(username)
                    log_access(username, "login")
                    st.success("Login realizado com sucesso!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos!")
                    log_access(username, "failed_login")
            else:
                st.warning("Preencha todos os campos!")

def admin_login():
    """Formulário de login para painel administrativo"""
    st.subheader("Painel Administrativo")
    st.warning("⚠️ Acesso restrito apenas para administradores")
    
    with st.form("admin_login_form"):
        username = st.text_input("Usuário Administrador")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button("Acessar Painel")
        
        if submit_button:
            if username and password:
                if check_password(username, password) and is_admin(username):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.is_admin = True
                    st.session_state.access_mode = "admin_panel"
                    update_last_login(username)
                    log_access(username, "admin_login")
                    st.success("Acesso ao painel administrativo autorizado!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Credenciais inválidas ou usuário sem privilégios administrativos!")
                    log_access(username, "failed_admin_login")
            else:
                st.warning("Preencha todos os campos!")

def password_change_form():
    """Formulário para alteração de senha"""
    st.subheader("Alterar Senha")
    st.info("Qualquer usuário pode alterar sua própria senha aqui")
    
    with st.form("password_change_form"):
        username = st.text_input("Usuário")
        old_password = st.text_input("Senha Atual", type="password")
        new_password = st.text_input("Nova Senha", type="password")
        confirm_password = st.text_input("Confirmar Nova Senha", type="password")
        submit_button = st.form_submit_button("Alterar Senha")
        
        if submit_button:
            if not all([username, old_password, new_password, confirm_password]):
                st.warning("Preencha todos os campos!")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem!")
            elif len(new_password) < 4:
                st.error("A nova senha deve ter pelo menos 4 caracteres!")
            else:
                success, message = change_password(username, old_password, new_password)
                if success:
                    st.success(message)
                    log_access(username, "password_change")
                    st.info("Redirecionando para o login...")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(message)

# --- Painel Administrativo ---
def admin_panel():
    """Painel de administração de usuários"""
    st.title("👨‍💼 Painel de Administração")
    st.markdown("---")
    
    # Header com informações do admin
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.info(f"Administrador: {st.session_state.username}")
    with col2:
        users = load_users()
        st.info(f"Total de usuários: {len(users)}")
    with col3:
        if st.button("🚪 Logout"):
            log_access(st.session_state.username, "logout")
            for key in ['authenticated', 'username', 'is_admin', 'access_mode']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Botão para voltar ao dashboard
    st.sidebar.header("🔄 Navegação")
    if st.sidebar.button("📊 Voltar ao Dashboard"):
        st.session_state.access_mode = "dashboard"
        st.rerun()
    
    # Tabs do painel
    tab1, tab2, tab3 = st.tabs(["👥 Gerenciar Usuários", "➕ Criar Usuário", "📊 Logs de Acesso"])
    
    with tab1:
        user_management_tab()
    
    with tab2:
        create_user_tab()
    
    with tab3:
        access_logs_tab()

def user_management_tab():
    """Tab de gerenciamento de usuários"""
    st.subheader("Lista de Usuários")
    
    users = load_users()
    if not users:
        st.warning("Nenhum usuário encontrado.")
        return
    
    # Criar DataFrame para exibição
    user_data = []
    for username, info in users.items():
        user_data.append({
            "Usuário": username,
            "Nome Completo": info.get("full_name", "N/A"),
            "Email": info.get("email", "N/A"),
            "Função": info.get("role", "user"),
            "Criado em": info.get("created_at", "N/A")[:19] if info.get("created_at") else "N/A",
            "Último Login": info.get("last_login", "Nunca")[:19] if info.get("last_login") else "Nunca"
        })
    
    df_users = pd.DataFrame(user_data)
    st.dataframe(df_users, use_container_width=True)
    
    # Seção de edição
    st.markdown("### ✏️ Editar Usuário")
    
    selected_user = st.selectbox(
        "Selecione o usuário para editar:",
        options=list(users.keys()),
        index=None,
        placeholder="Escolha um usuário..."
    )
    
    if selected_user:
        user_info = users[selected_user]
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.form(f"edit_user_{selected_user}"):
                st.write(f"**Editando: {selected_user}**")
                
                new_email = st.text_input("Email:", value=user_info.get("email", ""))
                new_full_name = st.text_input("Nome Completo:", value=user_info.get("full_name", ""))
                new_role = st.selectbox("Função:", ["user", "admin"], 
                                      index=0 if user_info.get("role") == "user" else 1)
                new_password = st.text_input("Nova Senha (deixe em branco para não alterar):", 
                                           type="password")
                
                col_update, col_delete = st.columns(2)
                
                with col_update:
                    update_button = st.form_submit_button("💾 Atualizar", type="primary")
                
                with col_delete:
                    delete_button = st.form_submit_button("🗑️ Excluir", type="secondary")
                
                if update_button:
                    success, message = update_user(
                        selected_user, 
                        email=new_email if new_email else None,
                        full_name=new_full_name if new_full_name else None,
                        role=new_role,
                        new_password=new_password if new_password else None
                    )
                    if success:
                        st.success(message)
                        log_access(st.session_state.username, f"updated_user_{selected_user}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(message)
                
                if delete_button:
                    success, message = delete_user(selected_user)
                    if success:
                        st.success(message)
                        log_access(st.session_state.username, f"deleted_user_{selected_user}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(message)
        
        with col2:
            # Informações do usuário selecionado
            st.write("### 📋 Informações do Usuário")
            st.write(f"**Usuário:** {selected_user}")
            st.write(f"**Email:** {user_info.get('email', 'N/A')}")
            st.write(f"**Nome:** {user_info.get('full_name', 'N/A')}")
            st.write(f"**Função:** {user_info.get('role', 'user')}")
            st.write(f"**Criado:** {user_info.get('created_at', 'N/A')[:19] if user_info.get('created_at') else 'N/A'}")
            st.write(f"**Último Login:** {user_info.get('last_login', 'Nunca')[:19] if user_info.get('last_login') else 'Nunca'}")

def create_user_tab():
    """Tab de criação de usuário"""
    st.subheader("Criar Novo Usuário")
    
    with st.form("create_user_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_username = st.text_input("Usuário*:")
            new_password = st.text_input("Senha*:", type="password")
            new_role = st.selectbox("Função:", ["user", "admin"])
        
        with col2:
            new_email = st.text_input("Email:")
            new_full_name = st.text_input("Nome Completo:")
            confirm_password = st.text_input("Confirmar Senha*:", type="password")
        
        create_button = st.form_submit_button("➕ Criar Usuário", type="primary")
        
        if create_button:
            if not all([new_username, new_password, confirm_password]):
                st.error("Preencha todos os campos obrigatórios!")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem!")
            elif len(new_password) < 4:
                st.error("A senha deve ter pelo menos 4 caracteres!")
            else:
                success, message = create_user(
                    new_username, 
                    new_password, 
                    new_email or f"{new_username}@lhg.com",
                    new_full_name or new_username,
                    new_role
                )
                if success:
                    st.success(message)
                    log_access(st.session_state.username, f"created_user_{new_username}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(message)

def access_logs_tab():
    """Tab de visualização dos logs de acesso"""
    st.subheader("Logs de Acesso")
    
    if os.path.exists("access_logs.txt"):
        try:
            with open("access_logs.txt", "r", encoding="utf-8") as f:
                logs = f.readlines()
            
            if logs:
                # Mostrar apenas os últimos 100 logs
                recent_logs = logs[-100:]
                recent_logs.reverse()  # Mais recentes primeiro
                
                st.text_area(
                    "Últimos 100 registros (mais recentes primeiro):",
                    value="\n".join(recent_logs),
                    height=400
                )
                
                # Botão para limpar logs
                if st.button("🗑️ Limpar Logs"):
                    with open("access_logs.txt", "w", encoding="utf-8") as f:
                        f.write("")
                    st.success("Logs limpos com sucesso!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.info("Nenhum log de acesso encontrado.")
        except Exception as e:
            st.error(f"Erro ao ler logs: {str(e)}")
    else:
        st.info("Arquivo de logs não encontrado.")

# --- Funções do Dashboard (mantenha todas as funções originais aqui) ---
@st.cache_data
def load_and_preprocess_data(file_path, start_date, end_date, cache_key):
    try:
        # Descriptografa o arquivo na memória
        decrypted_file = decrypt_file_in_memory(file_path)
        if not decrypted_file:
            return pd.DataFrame(), pd.DataFrame()

        df = pd.read_excel(decrypted_file)

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
    
    try:
        insights = []
        
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
        
        return insights
        
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
def dashboard_main():
    """Função principal do dashboard"""
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
            for key in ['authenticated', 'username', 'is_admin', 'access_mode']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # Sidebar para configurações
    st.sidebar.header("📋 Configurações")
    st.sidebar.info(f"Usuário: {st.session_state.get('username', 'Desconhecido')}")
    st.sidebar.info(f"🔄 Última atualização: {update_info.get('last_update', 'N/A')[:19]}")
    
    # Botão para acessar painel admin (se for admin)
    if st.session_state.get('is_admin', False):
        st.sidebar.header("👨‍💼 Administração")
        if st.sidebar.button("Painel Administrativo"):
            st.session_state.access_mode = "admin_panel"
            st.rerun()

    # Resto do dashboard (filtros, gráficos, etc.) - continua igual...
    # [O resto do código do dashboard permanece o mesmo]
    
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
    
    # Caminho para o arquivo criptografado
    file_path = ENCRYPTED_FILENAME
    
    if not os.path.exists(file_path):
        st.error("Arquivo de dados não encontrado! Certifique-se de que 'Diesel-area.encrypted' está na mesma pasta que o script.")
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

def main():
    # Verificar autenticação
    if not st.session_state.get('authenticated', False):
        login_form()
        return
    
    # Verificar modo de acesso
    access_mode = st.session_state.get('access_mode', 'dashboard')
    
    if access_mode == "admin_panel":
        admin_panel()
        return
    
    # Dashboard principal
    dashboard_main()

if __name__ == "__main__":
    main()