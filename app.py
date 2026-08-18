import streamlit as st
import requests
import json
import time
import pandas as pd

API_BASE = "https://api-cnis-4rxm.onrender.com"

st.set_page_config(page_title="Previdência Fácil", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .metric-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 15px; }
    .badge-success { background-color: #dcfce7; color: #15803d; padding: 4px 12px; border-radius: 9999px; font-weight: 600; display: inline-block; }
    .badge-warning { background-color: #fef9c3; color: #a16207; padding: 4px 12px; border-radius: 9999px; font-weight: 600; display: inline-block; }
    .badge-danger { background-color: #fee2e2; color: #b91c1c; padding: 4px 12px; border-radius: 9999px; font-weight: 600; display: inline-block; }
    .audit-error-card { background-color: #fffaf0; border-left: 4px solid #dd6b20; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/942/942748.png", width=64)
    st.title("Previdência Fácil")
    st.caption("v3.0 • Auditoria & Extração Inteligente")
    st.markdown("---")
    st.success("🟢 API Online")
    st.markdown("---")
    st.info("""
    1. Use **Extração de Dados** para PDFs escaneados.
    2. Depois envie todos os PDFs para **Auditoria**.
    """)

st.title("⚖️ Previdência Fácil")
st.markdown("Plataforma de pré-análise documental e auditoria previdenciária do INSS.")
st.markdown("---")

opcao = st.sidebar.radio(
    "Selecione a funcionalidade:",
    ["Auditoria de Processo", "Extração de Dados com IA"]
)

# =============================================
# ABA 1: AUDITORIA DE PROCESSO
# =============================================
if opcao == "Auditoria de Processo":
    st.header("🩺 Auditoria Previdenciária")
    arquivos = st.file_uploader("Selecione todos os PDFs do processo (CNIS, RG, RGP, Laudos):", type=["pdf"], accept_multiple_files=True)

    if st.button("🚀 Processar Auditoria", disabled=not arquivos):
        progresso = st.progress(0)
        status_box = st.status("Processando processo completo...", expanded=True)

        try:
            files = [("files", (arq.name, arq.getvalue(), "application/pdf")) for arq in arquivos]
            status_box.write("📤 Enviando documentos...")
            resp = requests.post(f"{API_BASE}/analisar-processo-completo", files=files, timeout=300)
            progresso.progress(70)

            if resp.status_code == 200:
                dados = resp.json()
                progresso.progress(100)
                status_box.update(label="Auditoria Concluída!", state="complete", expanded=False)
                time.sleep(0.3)
                progresso.empty()

                if not dados.get("success"):
                    st.error(f"Erro: {dados.get('error')}")
                else:
                    pessoais = dados.get("dados_pessoais", {}) or {}
                    aud = dados.get("auditoria", {}) or {}
                    calc = dados.get("calculo", {}) or {}

                    st.markdown("##")
                    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

                    with kpi1:
                        st.metric("Titular", (pessoais.get("nome") or "N/D")[:18])
                        st.caption(f"CPF: {pessoais.get('cpf', 'N/D')}")

                    with kpi2:
                        st.metric("Serviço", aud.get("servico_detectado", "Geral"))
                        st.caption(f"NIT: {pessoais.get('nit', 'N/D')}")

                    with kpi3:
                        tempo_anos = calc.get("tempo_contribuicao_anos")
                        tempo_exibicao = f"{tempo_anos}a {calc.get('tempo_contribuicao_meses',0)}m" if tempo_anos is not None else "N/D"
                        st.metric("Tempo", tempo_exibicao)
                        st.caption(f"Carência: {calc.get('carencia_meses', 0)} meses")

                    with kpi4:
                        status_geral = aud.get("status_geral", "")
                        if "APROVA" in status_geral.upper() or "🟢" in status_geral:
                            st.markdown('<span class="badge-success">APTO</span>', unsafe_allow_html=True)
                        elif "RISCO" in status_geral.upper() or "🟡" in status_geral:
                            st.markdown('<span class="badge-warning">RISCO</span>', unsafe_allow_html=True)
                        else:
                            st.markdown('<span class="badge-danger">IMPEDIMENTO</span>', unsafe_allow_html=True)

                    st.markdown("---")

                    tab1, tab2, tab3, tab4 = st.tabs(["Diagnóstico", "Simulações", "Vínculos", "Documentos"])

                    with tab1:
                        erros = aud.get("diagnostico_erros", []) or []
                        if erros:
                            for erro in erros:
                                st.markdown(f"""
                                **🔴 {erro.get('tipo_de_erro')}**  
                                {erro.get('descricao')}  
                                💡 {erro.get('como_corrigir')}  
                                ---
                                """)
                        else:
                            st.success("Nenhuma inconformidade encontrada.")

                    with tab2:
                        sim = calc.get("simulacao", {}) or {}
                        for chave, valor in sim.items():
                            elegivel = "🟢" if valor.get("elegivel") else "🔴"
                            st.write(f"**{chave.replace('_', ' ').title()}:** {elegivel}")

                    with tab3:
                        vinculos = dados.get("vinculos", []) or []
                        if vinculos:
                            df = pd.DataFrame(vinculos)
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            st.info("Nenhum vínculo encontrado.")

                    with tab4:
                        docs = dados.get("documentos_analisados", []) or []
                        for doc in docs:
                            st.write(f"📄 {doc}")

            else:
                status_box.update(label=f"Erro HTTP {resp.status_code}", state="error")
                st.error(f"Erro HTTP {resp.status_code}")

        except requests.exceptions.Timeout:
            st.error("⏳ Timeout. Tente novamente com menos arquivos.")
        except Exception as e:
            st.error(f"Exceção: {e}")

# =============================================
# ABA 2: EXTRAÇÃO DE DADOS COM IA
# =============================================
elif opcao == "Extração de Dados com IA":
    st.header("🧠 Extração de Dados de Documentos Escaneados")
    st.markdown("Envie um PDF escaneado (RG, CPF, CTPS, CNIS) e a IA extrairá os dados.")

    arquivo_extra = st.file_uploader("Escolha um PDF escaneado", type=["pdf"], key="extra_ia")

    if st.button("Extrair Dados", disabled=not arquivo_extra):
        with st.spinner("Extraindo..."):
            try:
                files = {"file": (arquivo_extra.name, arquivo_extra.getvalue(), "application/pdf")}
                resp = requests.post(f"{API_BASE}/extrair-dados-ia", files=files, timeout=180)
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("success"):
                        st.success("✅ Extração concluída!")
                        extra = dados.get("dados", {})
                        st.write(f"**Nome:** {extra.get('nome')}")
                        st.write(f"**CPF:** {extra.get('cpf')}")
                        st.write(f"**NIT:** {extra.get('nit')}")
                        st.write(f"**Nascimento:** {extra.get('data_nascimento')}")
                        st.write(f"**Mãe:** {extra.get('nome_mae')}")
                        st.write(f"**Sexo:** {extra.get('sexo')}")
                        if extra.get("vinculos"):
                            st.subheader("Vínculos")
                            for v in extra["vinculos"]:
                                st.write(f"- {v.get('empregador')} | {v.get('data_inicio')} a {v.get('data_fim')}")
                    else:
                        st.error(f"Erro: {dados.get('error')}")
                else:
                    st.error(f"Erro HTTP {resp.status_code}")
            except Exception as e:
                st.error(f"Exceção: {e}")
