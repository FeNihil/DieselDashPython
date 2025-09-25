import json,os,streamlit as st,pandas as pd,plotly.express as px
from datetime import date,timedelta,datetime
import hashlib,base64,io,time
from cryptography.fernet import Fernet

# Configurações globais
ENCRYPTED_FILENAME,ENCRYPTED_USERS_FILE,ADMIN_USERNAME="Diesel-area.encrypted","users.encrypted","admin"
PRIMARY_COLOR,SECONDARY_COLOR="#FF6600","#808080"

# Inicialização da criptografia
try:
    fernet=Fernet(base64.urlsafe_b64encode(bytes.fromhex(st.secrets["HEX_KEY_STRING"])))
except:
    st.error("❌ Erro na chave de criptografia");fernet=None

def decrypt_file(path):
    if not fernet:return None
    try:
        with open(path,"rb") as f:data=f.read()
        return io.BytesIO(fernet.decrypt(data))
    except:st.error(f"❌ Erro ao descriptografar {path}");return None

def crypt_users(users,mode='load'):
    if not fernet:return {} if mode=='load' else False
    try:
        if mode=='load':
            if not os.path.exists(ENCRYPTED_USERS_FILE):return {}
            with open(ENCRYPTED_USERS_FILE,'rb') as f:
                return json.loads(fernet.decrypt(f.read()).decode('utf-8'))
        else:
            with open(ENCRYPTED_USERS_FILE,'wb') as f:
                f.write(fernet.encrypt(json.dumps(users,ensure_ascii=False).encode('utf-8')))
            return True
    except:return {} if mode=='load' else False

def get_update_info():
    try:
        with open('last_update.json','r') as f:return json.load(f)
    except:return {"timestamp":0,"last_update":"Não disponível"}

def hash_pwd(pwd):return hashlib.sha256(str.encode(pwd)).hexdigest()

def check_user(user,pwd):
    users=crypt_users({},'load')
    return user in users and users[user]["password"]==hash_pwd(pwd)

def is_admin(user):
    users=crypt_users({},'load')
    return user in users and users[user].get("role")=="admin"

def create_user(user,pwd,email,name,role="user"):
    users=crypt_users({},'load')
    if user in users:return False,"Usuário já existe"
    users[user]={"password":hash_pwd(pwd),"role":role,"email":email,"full_name":name,
                 "created_at":datetime.now().isoformat(),"last_login":None}
    return (True,"Usuário criado") if crypt_users(users,'save') else (False,"Erro ao salvar")

def update_user(user,email=None,name=None,role=None,pwd=None):
    users=crypt_users({},'load')
    if user not in users:return False,"Usuário não encontrado"
    if email:users[user]["email"]=email
    if name:users[user]["full_name"]=name
    if role:users[user]["role"]=role
    if pwd:users[user]["password"]=hash_pwd(pwd)
    return (True,"Atualizado") if crypt_users(users,'save') else (False,"Erro")

def delete_user(user):
    if user==ADMIN_USERNAME:return False,"Não pode remover admin"
    if user==st.session_state.get('username'):return False,"Não pode remover próprio usuário"
    users=crypt_users({},'load')
    if user not in users:return False,"Usuário não encontrado"
    del users[user]
    return (True,"Removido") if crypt_users(users,'save') else (False,"Erro")

def change_pwd(user,old,new):
    users=crypt_users({},'load')
    if user not in users:return False,"Usuário não encontrado"
    if users[user]["password"]!=hash_pwd(old):return False,"Senha incorreta"
    users[user]["password"]=hash_pwd(new)
    return (True,"Senha alterada") if crypt_users(users,'save') else (False,"Erro")

def log_access(user,action="login"):
    try:
        with open("access_logs.txt","a",encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {user} | {action}\n")
    except:pass

def login_ui():
    st.title("🔐 Login - Dashboard LHG")
    st.markdown("---")
    mode=st.radio("Modo:",["Login Normal","Painel Admin","Alterar Senha"],horizontal=True)

    if mode=="Login Normal":
        with st.form("login"):
            user,pwd=st.text_input("Usuário"),st.text_input("Senha",type="password")
            if st.form_submit_button("Entrar") and user and pwd:
                if check_user(user,pwd):
                    st.session_state.update(authenticated=True,username=user,is_admin=is_admin(user),access_mode="dashboard")
                    users=crypt_users({},'load');users[user]["last_login"]=datetime.now().isoformat();crypt_users(users,'save')
                    log_access(user);st.success("Login OK");time.sleep(1);st.rerun()
                else:st.error("Credenciais inválidas");log_access(user,"failed_login")

    elif mode=="Painel Admin":
        with st.form("admin_login"):
            user,pwd=st.text_input("Admin"),st.text_input("Senha",type="password")
            if st.form_submit_button("Acessar") and user and pwd:
                if check_user(user,pwd) and is_admin(user):
                    st.session_state.update(authenticated=True,username=user,is_admin=True,access_mode="admin_panel")
                    log_access(user,"admin_login");st.success("Admin OK");time.sleep(1);st.rerun()
                else:st.error("Sem privilégios admin")

    else:
        with st.form("pwd_change"):
            user,old,new,conf=st.text_input("Usuário"),st.text_input("Senha Atual",type="password"),st.text_input("Nova Senha",type="password"),st.text_input("Confirmar",type="password")
            if st.form_submit_button("Alterar"):
                if not all([user,old,new,conf]):st.warning("Preencha todos os campos")
                elif new!=conf:st.error("Senhas não coincidem")
                elif len(new)<4:st.error("Mínimo 4 caracteres")
                else:
                    ok,msg=change_pwd(user,old,new)
                    if ok:st.success(msg);log_access(user,"pwd_change");time.sleep(2);st.rerun()
                    else:st.error(msg)

def admin_ui():
    st.title("👨‍💼 Painel Admin")
    st.markdown("---")

    col1,col2,col3=st.columns([2,2,1])
    with col1:st.info(f"Admin: {st.session_state.username}")
    with col2:st.info(f"Usuários: {len(crypt_users({},'load'))}")
    with col3:
        if st.button("🚪 Logout"):
            log_access(st.session_state.username,"logout")
            for k in ['authenticated','username','is_admin','access_mode']:
                if k in st.session_state:del st.session_state[k]
            st.rerun()

    if st.sidebar.button("📊 Dashboard"):st.session_state.access_mode="dashboard";st.rerun()

    tab1,tab2,tab3=st.tabs(["👥 Usuários","➕ Criar","📊 Logs"])

    with tab1:
        users=crypt_users({},'load')
        if users:
            # ✅ CÓDIGO CORRIGIDO
            df=pd.DataFrame([{"Usuário":u,"Nome":v.get("full_name","N/A"),"Email":v.get("email","N/A"),
                            "Função":v.get("role","user"),"Criado":v.get("created_at","N/A")[:10],
                            "Login":v.get("last_login","N/A")[:10]} for u,v in users.items()])

            sel=st.selectbox("Editar:",list(users.keys()),index=None)
            if sel:
                info=users[sel]
                with st.form(f"edit_{sel}"):
                    email,name=st.text_input("Email:",info.get("email","")),st.text_input("Nome:",info.get("full_name",""))
                    role,pwd=st.selectbox("Função:",["user","admin"],index=0 if info.get("role")=="user" else 1),st.text_input("Nova Senha:",type="password")

                    col1,col2=st.columns(2)
                    with col1:upd=st.form_submit_button("💾 Atualizar")
                    with col2:del_=st.form_submit_button("🗑️ Excluir")

                    if upd:
                        ok,msg=update_user(sel,email or None,name or None,role,pwd or None)
                        if ok:st.success(msg);log_access(st.session_state.username,f"updated_{sel}");time.sleep(1);st.rerun()
                        else:st.error(msg)
                    if del_:
                        ok,msg=delete_user(sel)
                        if ok:st.success(msg);log_access(st.session_state.username,f"deleted_{sel}");time.sleep(1);st.rerun()
                        else:st.error(msg)

    with tab2:
        with st.form("create"):
            col1,col2=st.columns(2)
            with col1:user,pwd,role=st.text_input("Usuário*:"),st.text_input("Senha*:",type="password"),st.selectbox("Função:",["user","admin"])
            with col2:email,name,conf=st.text_input("Email:"),st.text_input("Nome:"),st.text_input("Confirmar*:",type="password")

            if st.form_submit_button("➕ Criar"):
                if not all([user,pwd,conf]):st.error("Campos obrigatórios!")
                elif pwd!=conf:st.error("Senhas diferentes!")
                elif len(pwd)<4:st.error("Mínimo 4 caracteres!")
                else:
                    ok,msg=create_user(user,pwd,email or f"{user}@lhg.com",name or user,role)
                    if ok:st.success(msg);log_access(st.session_state.username,f"created_{user}");time.sleep(1);st.rerun()
                    else:st.error(msg)

    with tab3:
        if os.path.exists("access_logs.txt"):
            try:
                with open("access_logs.txt","r",encoding="utf-8") as f:logs=f.readlines()
                if logs:
                    st.text_area("Últimos logs:",value="\n".join(logs[-100:][::-1]),height=400)
                    if st.button("🗑️ Limpar"):
                        with open("access_logs.txt","w") as f:f.write("")
                        st.success("Limpo!");time.sleep(1);st.rerun()
                else:st.info("Sem logs")
            except:st.error("Erro ao ler logs")
        else:st.info("Arquivo de logs não encontrado")

@st.cache_data
def load_data(path,start,end,cache_key):
    try:
        file=decrypt_file(path)
        if not file:return pd.DataFrame(),pd.DataFrame()

        df=pd.read_excel(file).rename(columns={
            'data de Inclusão':'DataInclusao','Quantidade':'ConsumoDiesel',
            'Valo Unitário':'CustoUnitario','Valor Total':'CustoTotalAbastecimento',
            'Área':'Setor','Dia':'DataConsumo'})

        df['DataInclusao'],df['DataConsumo']=pd.to_datetime(df['DataInclusao']),pd.to_datetime(df['DataConsumo'])
        df=df[df['Setor'].isin(['Tup','Rep'])].copy()
        df['Setor']=df['Setor'].replace({'Tup':'Expedição','Rep':'Peneiramento'})

        for col in ['ConsumoDiesel','CustoUnitario','CustoTotalAbastecimento']:
            df[col]=pd.to_numeric(df[col],errors='coerce')
        df.dropna(subset=['ConsumoDiesel','CustoUnitario','CustoTotalAbastecimento'],inplace=True)

        if start and end:
            df=df[(df['DataConsumo']>=pd.to_datetime(start))&(df['DataConsumo']<=pd.to_datetime(end))]

        daily=df.groupby(['DataConsumo','Setor']).agg(ConsumoDiario=('ConsumoDiesel','sum'),CustoDiario=('CustoTotalAbastecimento','sum')).reset_index()
        daily=daily.sort_values(['DataConsumo','Setor'])
        daily['ConsumoAcumulado']=daily.groupby('Setor')['ConsumoDiario'].cumsum()
        daily['CustoAcumulado']=daily.groupby('Setor')['CustoDiario'].cumsum()

        return daily,df
    except Exception as e:st.error(f"Erro: {e}");return pd.DataFrame(),pd.DataFrame()

def calc_kpis(df,period="month"):
    if df.empty:return {}
    try:
        today=pd.to_datetime(date.today())
        if period=="month":
            complete_days=df[(df['DataConsumo'].dt.month==today.month)&(df['DataConsumo']<today)]
        else:
            dates=sorted(df['DataConsumo'].unique())
            complete_days=df[df['DataConsumo']<dates[-1]] if len(dates)>1 else df

        exp_consume=df[df['Setor']=='Expedição']['ConsumoDiario'].sum()
        pen_consume=df[df['Setor']=='Peneiramento']['ConsumoDiario'].sum()
        total_consume=exp_consume+pen_consume

        exp_cost=df[df['Setor']=='Expedição']['CustoDiario'].sum()
        pen_cost=df[df['Setor']=='Peneiramento']['CustoDiario'].sum()
        total_cost=exp_cost+pen_cost

        avg_liter=total_cost/total_consume if total_consume>0 else 0
        days_count=len(complete_days['DataConsumo'].unique())
        daily_avg_consume=complete_days['ConsumoDiario'].sum()/days_count if days_count>0 else 0
        daily_avg_cost=complete_days['CustoDiario'].sum()/days_count if days_count>0 else 0

        if period=="month":
            last_day=(pd.Timestamp(today.year,today.month,1)+pd.DateOffset(months=1)-pd.DateOffset(days=1)).day
            remain=last_day-today.day
            proj_consume=total_consume+(daily_avg_consume*remain)
            proj_cost=total_cost+(daily_avg_cost*remain)
        else:proj_consume,proj_cost=total_consume,total_cost

        trend_data=complete_days.sort_values('DataConsumo').tail(7)
        trend='Estável'
        if len(trend_data)>=6:
            last3,prev3=trend_data['ConsumoDiario'].tail(3).mean(),trend_data['ConsumoDiario'].iloc[-6:-3].mean()
            if prev3>0:
                if last3>prev3*1.05:trend='Aumentando'
                elif last3<prev3*0.95:trend='Diminuindo'

        return {
            'total_consumed_period':total_consume,'avg_daily_consumption':daily_avg_consume,
            'projected_consumption':proj_consume,'trend':trend,
            'total_consumed_expedicao':exp_consume,'total_consumed_peneiramento':pen_consume,
            'total_cost_period':total_cost,'avg_daily_cost':daily_avg_cost,
            'projected_cost':proj_cost,'avg_liter_cost':avg_liter
        }
    except:return {}

def gen_insights(kpis,period="mês"):
    if not kpis:return ["Erro nos dados"]
    insights=[]

    if kpis['total_consumed_expedicao']>kpis['total_consumed_peneiramento']:
        insights.append(f"Expedição consome mais: {kpis['total_consumed_expedicao']:,.0f}L vs {kpis['total_consumed_peneiramento']:,.0f}L do Peneiramento.")
    else:
        insights.append(f"Peneiramento consome mais: {kpis['total_consumed_peneiramento']:,.0f}L vs {kpis['total_consumed_expedicao']:,.0f}L da Expedição.")

    insights.append(f"Consumo {kpis['trend'].lower()}, média {kpis['avg_daily_consumption']:,.0f}L/dia, custo R${kpis['avg_daily_cost']:,.0f}/dia.")

    if period=="mês":
        insights.append(f"Projeção: {kpis['projected_consumption']:,.0f}L, R${kpis['projected_cost']:,.0f}.")
    else:
        insights.append(f"Total período: {kpis['total_consumed_period']:,.0f}L, R${kpis['total_cost_period']:,.0f}.")

    return insights

def equipment_chart(df):
    if df.empty or 'Tag' not in df.columns:return None,None
    try:
        equip=df.groupby(['Tag','Setor'])['ConsumoDiesel'].sum().reset_index()
        exp_data,pen_data=equip[equip['Setor']=='Expedição'].sort_values('ConsumoDiesel'),equip[equip['Setor']=='Peneiramento'].sort_values('ConsumoDiesel')

        fig_exp=px.bar(exp_data,x='ConsumoDiesel',y='Tag',orientation='h',title="Expedição - Equipamentos",color_discrete_sequence=[PRIMARY_COLOR]) if not exp_data.empty else None
        fig_pen=px.bar(pen_data,x='ConsumoDiesel',y='Tag',orientation='h',title="Peneiramento - Equipamentos",color_discrete_sequence=[SECONDARY_COLOR]) if not pen_data.empty else None

        if fig_exp:fig_exp.update_layout(height=400,showlegend=False);fig_exp.update_traces(texttemplate='%{x:,.0f}L',textposition='outside')
        if fig_pen:fig_pen.update_layout(height=400,showlegend=False);fig_pen.update_traces(texttemplate='%{x:,.0f}L',textposition='outside')

        return fig_exp,fig_pen
    except:return None,None

def dashboard():
    info=get_update_info()

    col1,col2,col3=st.columns([1,4,1])
    with col1:
        if os.path.exists("Lhg-02.png"):st.image("Lhg-02.png",width=150)
        else:st.write("🏢 LHG")
    with col2:st.title("Dashboard Diesel");st.subheader("LHG Logística")
    with col3:
        if st.button("🚪 Logout"):
            log_access(st.session_state.username,"logout")
            for k in ['authenticated','username','is_admin','access_mode']:
                if k in st.session_state:del st.session_state[k]
            st.rerun()

    st.sidebar.header("📋 Config")
    st.sidebar.info(f"User: {st.session_state.get('username')}")
    st.sidebar.info(f"Update: {info.get('last_update','N/A')[:19]}")

    if st.session_state.get('is_admin'):
        st.sidebar.header("👨‍💼 Admin")
        if st.sidebar.button("Painel Admin"):st.session_state.access_mode="admin_panel";st.rerun()

    st.sidebar.header("📅 Filtros")
    filter_type=st.sidebar.selectbox("Tipo",["Mês Atual","Período Personalizado","Mês Específico"])

    start,end,period_label,period_type=None,None,"mês","month"

    if filter_type=="Período Personalizado":
        start,end=st.sidebar.date_input("Início",date.today()-timedelta(30)),st.sidebar.date_input("Fim",date.today())
        period_label,period_type=f"período {start:%d/%m/%Y} a {end:%d/%m/%Y}","custom"
    elif filter_type=="Mês Específico":
        months=["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
        month,year=st.sidebar.selectbox("Mês",months),st.sidebar.selectbox("Ano",[datetime.now().year-i for i in range(3)])
        m_num=months.index(month)+1
        start,end=date(year,m_num,1),(date(year+1,1,1) if m_num==12 else date(year,m_num+1,1))-timedelta(1)
        period_label,period_type=f"{month} {year}","custom"

    if not os.path.exists(ENCRYPTED_FILENAME):st.error("Arquivo não encontrado!");return

    with st.spinner("Carregando..."):
        df,df_orig=load_data(ENCRYPTED_FILENAME,start,end,info.get('timestamp',0))

    if df.empty:st.error("Sem dados válidos");return

    kpis=calc_kpis(df,period_type)
    insights=gen_insights(kpis,period_label)

    # CSS
    st.markdown(f"""<style>
    .stMetric{{background:#f0f2f6;border-radius:10px;padding:15px;margin:10px;box-shadow:2px 2px 5px rgba(0,0,0,0.1);}}
    .stMetric label{{color:{SECONDARY_COLOR};font-weight:bold;}}
    .stMetric div[data-testid="stMetricValue"]{{color:{PRIMARY_COLOR};font-size:2.5em;}}
    </style>""",unsafe_allow_html=True)

    # KPIs
    st.header("📊 KPIs")
    col1,col2,col3=st.columns(3)
    with col1:st.metric(f"Consumo ({period_label.title()})",f"{kpis['total_consumed_period']:,.0f} L")
    with col2:st.metric("Média Diária",f"{kpis['avg_daily_consumption']:,.0f} L")
    with col3:st.metric("Projeção" if period_type=="month" else "Total",f"{kpis['projected_consumption']:,.0f} L")

    col4,col5,col6=st.columns(3)
    with col4:st.metric(f"Custo ({period_label.title()})",f"R${kpis['total_cost_period']:,.0f}")
    with col5:st.metric("Custo Diário",f"R${kpis['avg_daily_cost']:,.0f}")
    with col6:st.metric("Proj.Custo" if period_type=="month" else "Custo Total",f"R${kpis['projected_cost']:,.0f}")

    col7,col8=st.columns(2)
    with col7:st.metric("Custo/Litro",f"R${kpis['avg_liter_cost']:.2f}")
    with col8:st.metric("Tendência",kpis['trend'])

    # Gráficos
    st.header("📈 Gráficos")
    col1,col2=st.columns(2)

    with col1:
        fig_line=px.line(df,x='DataConsumo',y='ConsumoDiario',color='Setor',title="Evolução Diária",
                        color_discrete_map={'Expedição':PRIMARY_COLOR,'Peneiramento':SECONDARY_COLOR})
        st.plotly_chart(fig_line,use_container_width=True)

    with col2:
        comp_data=pd.DataFrame({'Setor':['Expedição','Peneiramento'],
                               'Consumo':[kpis['total_consumed_expedicao'],kpis['total_consumed_peneiramento']]})
        fig_bar=px.bar(comp_data,x='Setor',y='Consumo',title="Comparação Acumulada",color='Setor',
                      color_discrete_map={'Expedição':PRIMARY_COLOR,'Peneiramento':SECONDARY_COLOR})
        st.plotly_chart(fig_bar,use_container_width=True)

    # Equipamentos
    st.header("🚛 Por Equipamento")
    if not df_orig.empty:
        fig_exp,fig_pen=equipment_chart(df_orig)
        col1,col2=st.columns(2)
        with col1:
            if fig_exp:st.plotly_chart(fig_exp,use_container_width=True)
            else:st.warning("Sem dados Expedição")
        with col2:
            if fig_pen:st.plotly_chart(fig_pen,use_container_width=True)
            else:st.warning("Sem dados Peneiramento")

    # Insights
    st.header("🔍 Insights")
    for i,insight in enumerate(insights,1):st.write(f"**{i}.** {insight}")

    # Dados
    st.header("📋 Dados")
    st.dataframe(df,use_container_width=True)

    # Sidebar info
    st.sidebar.header("ℹ️ Info")
    st.sidebar.info(f"Registros: {len(df)}")
    if not df.empty:st.sidebar.info(f"Período: {df['DataConsumo'].min():%d/%m/%Y} - {df['DataConsumo'].max():%d/%m/%Y}")
    if st.sidebar.button("🔄 Refresh"):st.cache_data.clear();st.rerun()

# Config da página
st.set_page_config(page_title="Dashboard Diesel - LHG",page_icon="⛽",layout="wide")

def main():
    if not st.session_state.get('authenticated'):login_ui();return

    mode=st.session_state.get('access_mode','dashboard')
    if mode=="admin_panel":admin_ui()
    else:dashboard()

if __name__=="__main__":main()