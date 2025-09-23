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

# -----------------------------
# Configuração base da página
# -----------------------------
st.set_page_config(page_title="Home - Dashboard LHG", page_icon="🔐", layout="centered")  # apenas aqui, 1 vez [web:22]

# -----------------------------
# Constantes/arquivos
# -----------------------------
ENCRYPTED_FILENAME = "Diesel-area.encrypted"
ENCRYPTED_USERS_FILE = "users.encrypted"
ADMIN_USERNAME = "admin"

# -----------------------------
# Chave Fernet via secrets
# -----------------------------
HEX_KEY_STRING = st.secrets["HEX_KEY_STRING"]  # conforme seu projeto [web:15]
fernet = None
if HEX_KEY_STRING:
    try:
        key_bytes = bytes.fromhex(HEX_KEY_STRING)
        ENCRYPTION_KEY = base64.urlsafe_b64encode(key_bytes)
        fernet = Fernet(ENCRYPTION_KEY)
    except ValueError as e:
        st.error(f"❌ Erro na chave de criptografia. Verifique HEX_KEY_STRING: {e}")
else:
    st.error("❌ Chave de criptografia ausente em st.secrets!")

# -----------------------------
# Criptografia arquivos
# -----------------------------
def encrypt_users_file(users_data):
    if not fernet:
        return False
    try:
        json_data = json.dumps(users_data, indent=2, ensure_ascii=False)
        data_bytes = json_data.encode("utf-8")
        encrypted_data = fernet.encrypt(data_bytes)
        with open(ENCRYPTED_USERS_FILE, "wb") as f:
            f.write(encrypted_data)
        return True
    except Exception as e:
        st.error(f"Erro ao criptografar usuários: {str(e)}")
        return False

def decrypt_users_file():
    if not fernet:
        return {}
    try:
        if not os.path.exists(ENCRYPTED_USERS_FILE):
            return {}
        with open(ENCRYPTED_USERS_FILE, "rb") as f:
            enc = f.read()
        dec = fernet.decrypt(enc)
        return json.loads(dec.decode("utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        st.error(f"Erro ao descriptografar usuários: {str(e)}")
        return {}

# -----------------------------
# Utilidades de usuários
# -----------------------------
def load_users():
    return decrypt_users_file()

def save_users(users):
    return encrypt_users_file(users)

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password(username, password):
    users = load_users()
    if username in users:
        return users[username]["password"] == hash_password(password)
    return False

def is_admin(username):
    users = load_users()
    return username in users and users[username].get("role") == "admin"

def create_user(username, password, email, full_name, role="user"):
    users = load_users()
    if username in users:
        return False, "Usuário já existe"
    users[username] = {
        "password": hash_password(password),
        "role": role,
        "email": email,
        "full_name": full_name,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
    }
    if save_users(users):
        return True, "Usuário criado com sucesso"
    return False, "Erro ao salvar usuário"

def update_user(username, email=None, full_name=None, role=None, new_password=None):
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
    return False, "Erro ao salvar alterações"

def delete_user(username):
    if username == ADMIN_USERNAME:
        return False, "Não é possível remover o administrador"
    current_user = st.session_state.get("username")
    if username == current_user:
        return False, "Não é possível remover seu próprio usuário"
    users = load_users()
    if username not in users:
        return False, "Usuário não encontrado"
    del users[username]
    if save_users(users):
        return True, "Usuário removido com sucesso"
    return False, "Erro ao remover usuário"

def change_password(username, old_password, new_password):
    users = load_users()
    if username not in users:
        return False, "Usuário não encontrado"
    if users[username]["password"] != hash_password(old_password):
        return False, "Senha atual incorreta"
    users[username]["password"] = hash_password(new_password)
    if save_users(users):
        return True, "Senha alterada com sucesso"
    return False, "Erro ao alterar senha"

def update_last_login(username):
    users = load_users()
    if username in users:
        users[username]["last_login"] = datetime.now().isoformat()
        save_users(users)

def log_access(username, action="login"):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("access_logs.txt", "a", encoding="utf-8") as f:
            f.write(f"{ts} | {username} | {action}\n")
    except Exception as e:
        st.error(f"Erro ao registrar log: {str(e)}")

# -----------------------------
# UI: Login e Painel Admin
# -----------------------------
def normal_login():
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
                    st.error("Credenciais inválidas ou sem privilégios!")
                    log_access(username, "failed_admin_login")
            else:
                st.warning("Preencha todos os campos!")

def password_change_form():
    st.subheader("Alterar Senha")
    st.info("Qualquer usuário pode alterar sua própria senha")
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

def login_form():
    st.title("🔐 Login - Dashboard LHG Logística")
    st.markdown("---")
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

def user_management_tab():
    st.subheader("Lista de Usuários")
    users = load_users()
    if not users:
        st.warning("Nenhum usuário encontrado.")
        return
    user_data = []
    for username, info in users.items():
        user_data.append({
            "Usuário": username,
            "Nome Completo": info.get("full_name", "N/A"),
            "Email": info.get("email", "N/A"),
            "Função": info.get("role", "user"),
            "Criado em": info.get("created_at", "N/A")[:19] if info.get("created_at") else "N/A",
            "Último Login": info.get("last_login", "Nunca")[:19] if info.get("last_login") else "Nunca",
        })
    df_users = pd.DataFrame(user_data)
    st.dataframe(df_users, use_container_width=True)

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
                new_password = st.text_input("Nova Senha (opcional):", type="password")
                col_update, col_delete = st.columns(2)
                with col_update:
                    update_button = st.form_submit_button("💾 Atualizar", type="primary")
                with col_delete:
                    delete_button = st.form_submit_button("🗑️ Excluir", type="secondary")
                if update_button:
                    success, message = update_user(
                        selected_user,
                        email=new_email or None,
                        full_name=new_full_name or None,
                        role=new_role,
                        new_password=new_password or None,
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
            st.write("### 📋 Informações do Usuário")
            st.write(f"**Usuário:** {selected_user}")
            st.write(f"**Email:** {user_info.get('email', 'N/A')}")
            st.write(f"**Nome:** {user_info.get('full_name', 'N/A')}")
            st.write(f"**Função:** {user_info.get('role', 'user')}")
            st.write(f"**Criado:** {user_info.get('created_at', 'N/A')[:19] if user_info.get('created_at') else 'N/A'}")
            st.write(f"**Último Login:** {user_info.get('last_login', 'Nunca')[:19] if user_info.get('last_login') else 'Nunca'}")

def create_user_tab():
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
                    new_role,
                )
                if success:
                    st.success(message)
                    log_access(st.session_state.username, f"created_user_{new_username}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(message)

def access_logs_tab():
    st.subheader("Logs de Acesso")
    if os.path.exists("access_logs.txt"):
        try:
            with open("access_logs.txt", "r", encoding="utf-8") as f:
                logs = f.readlines()
            if logs:
                recent_logs = logs[-100:]
                recent_logs.reverse()
                st.text_area(
                    "Últimos 100 registros (mais recentes primeiro):",
                    value="\n".join(recent_logs),
                    height=400,
                )
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

def admin_panel():
    st.title("👨‍💼 Painel de Administração")
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.info(f"Administrador: {st.session_state.username}")
    with col2:
        users = load_users()
        st.info(f"Total de usuários: {len(users)}")
    with col3:
        if st.button("🚪 Logout"):
            log_access(st.session_state.username, "logout")
            for key in ["authenticated", "username", "is_admin", "access_mode"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    st.sidebar.header("🔄 Navegação")
    if st.sidebar.button("📊 Voltar ao Dashboard"):
        st.session_state.access_mode = "dashboard"
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["👥 Gerenciar Usuários", "➕ Criar Usuário", "📊 Logs de Acesso"])
    with tab1:
        user_management_tab()
    with tab2:
        create_user_tab()
    with tab3:
        access_logs_tab()

# -----------------------------
# Fluxo principal
# -----------------------------
# Inicializa estado
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "access_mode" not in st.session_state:
    st.session_state.access_mode = "dashboard"
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# Se não autenticado, mostra login
if not st.session_state.authenticated:
    login_form()
else:
    # Topbar: usuário e logout
    topcol1, topcol2, topcol3 = st.columns([3, 2, 1])
    with topcol1:
        st.success(f"Usuário: {st.session_state.username}")
    with topcol2:
        st.info("Acesso: Admin" if st.session_state.is_admin else "Acesso: Usuário")
    with topcol3:
        if st.button("🚪 Logout"):
            log_access(st.session_state.username, "logout")
            for key in ["authenticated", "username", "is_admin", "access_mode"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    st.markdown("---")

    # Se admin escolheu painel
    if st.session_state.access_mode == "admin_panel" and st.session_state.is_admin:
        admin_panel()
    else:
        # Dashboard de links (após login)
        st.title("🏠 Home - Dashboard LHG")
        st.write("Selecione uma página para abrir:")

        # Navegação oficial multipágina com page_link (sem st.navigation) [web:20][web:21]
        # Ajuste os caminhos conforme o nome real dos arquivos em seu repo.
        st.sidebar.header("Navegação")
        st.sidebar.page_link("1_Produção.py", label="📊 Produção")       # arquivo principal [web:20]
        st.sidebar.page_link("pages/2_Qualidade.py", label="🔬 Qualidade")  # subpágina [web:20]

        # Também pode expor botões na área principal:
        colA, colB = st.columns(2)
        with colA:
            st.page_link("1_Produção.py", label="➡️ Ir para Produção", help="Abrir página de Produção")  # [web:20]
        with colB:
            st.page_link("pages/2_Qualidade.py", label="➡️ Ir para Qualidade", help="Abrir página de Qualidade")  # [web:20]

        st.info("Dica: use a barra lateral para alternar entre as páginas de Produção e Qualidade.")
