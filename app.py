import streamlit as st
import requests
import json
import time
import pandas as pd

API_BASE = "https://api-cnis-4rxm.onrender.com"

st.set_page_config(page_title="Previdência Fácil | Auditoria Inteligente", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .metric-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 15px; }
    .badge-success { background-color: #dcfce7; color: #15803d; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; display: inline-block; }
    .badge-warning { background-color: #fef9c3; color: #a16207; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; display: inline-block; }
    .badge-danger { background-color: #fee2e2; color: #b91c1c; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; display: inline-block; }
    .audit-error-card { background-color: #fffaf0; border-left: 4px solid #dd6b20; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/942/942748.png", width=64)
    st.title("Previdência Fácil")
    st.caption("v2.5 • Auditoria & Extração Inteligente")
    st.markdown("---")
    st.markdown("### ⚙️ Status da Conexão")
    st.success("🟢 API Online (Render)")
    st.markdown(f"**Endpoint:** `{API_BASE}`")
    st.markdown("---")
    st.markdown("### 💡 Instruções")
    st.info("""
    1. Reúna os PDFs do processo.
    2. Use a aba de Extração para documentos escaneados.
    3. Depois envie os PDFs para auditoria completa.
    """)

st.title("⚖️ Painel de Auditoria Previdenciária")
st.markdown("Plataforma de pré-análise documental, contagem de tempo e conformidade normativa do INSS.")
st.markdown("---")

opcao = st.sidebar.radio(
    "Selecione a funcionalidade:",
    ["Upload CNIS", "Calcular Benefício", "Analisar Documento", "Consulta Processo", "Auditoria de Processo", "Extração de Dados com IA"]
)

if opcao == "Upload CNIS":
    st.header("📄 Enviar CNIS")
    arquivo = st.file_uploader("Escolha o PDF do CNIS", type=["pdf"])
    if arquivo is not None:
        if st.button("Processar CNIS"):
            with st.spinner("Processando PDF..."):
                try:
                    files = {"file": (arquivo.name, arquivo.getvalue(), "application/pdf")}
                    resp = requests.post(f"{API_BASE}/upload-cnis", files=files, timeout=90)
                    if resp.status_code == 200:
                        dados = resp.json()
                        if dados.get("success"):
                            st.success("✅ CNIS processado com sucesso!")
                            pessoais = dados.get("dados_pessoais", {})
                            st.subheader("Dados Pessoais")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Nome:** {pessoais.get('nome', 'N/D')}")
                                st.write(f"**NIT:** {pessoais.get('nit', 'N/D')}")
                                st.write(f"**CPF:** {pessoais.get('cpf', 'N/D')}")
                            with col2:
                                st.write(f"**Data de Nascimento:** {pessoais.get('data_nascimento', 'N/D')}")
                                st.write(f"**Nome da Mãe:** {pessoais.get('nome_mae', 'N/D')}")
                            st.subheader("Vínculos Empregatícios")
                            vinculos = dados.get("vinculos", [])
                            if vinculos:
                                for v in vinculos:
                                    st.markdown(f"""
                                    **Empregador:** {v.get('empregador', 'N/D')}  
                                    **Data Início:** {v.get('data_inicio', 'N/D')} | **Data Fim:** {v.get('data_fim', 'N/D')}  
                                    **Tipo Filiado:** {v.get('tipo_filiado', 'N/D')}  
                                    **Última Remuneração:** {v.get('ultima_remuneracao', 'N/D')} | **Indicador:** {v.get('indicador', 'N/D')}
                                    ---
                                    """)
                            else:
                                st.info("Nenhum vínculo encontrado.")
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")

elif opcao == "Calcular Benefício":
    st.header("🧮 Cálculo Previdenciário")
    nit = st.text_input("NIT do Segurado")
    sexo = st.selectbox("Sexo", ["M", "F"])
    if st.button("Calcular"):
        if not nit:
            st.warning("Digite o NIT.")
        else:
            with st.spinner("Calculando..."):
                try:
                    payload = {"nit": nit, "sexo": sexo}
                    resp = requests.post(f"{API_BASE}/calcular", json=payload, timeout=60)
                    if resp.status_code == 200:
                        dados = resp.json()
                        if dados.get("success"):
                            st.success("✅ Cálculo realizado!")
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Idade", dados.get("idade"))
                            col2.metric("Carência (meses)", dados.get("carencia_meses"))
                            col3.metric("Tempo de Contribuição", f"{dados.get('tempo_contribuicao_anos')}a {dados.get('tempo_contribuicao_meses')}m {dados.get('tempo_contribuicao_dias')}d")
                            sim = dados.get("simulacao", {})
                            for chave, valor in sim.items():
                                elegivel = "🟢 Elegível" if valor.get("elegivel") else "🔴 Não Elegível"
                                st.write(f"**{chave.replace('_', ' ').title()}:** {elegivel}")
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")

elif opcao == "Analisar Documento":
    st.header("🔍 Análise de Documento com IA")
    tipo_doc = st.text_input("Tipo de Documento", value="PPP")
    texto_doc = st.text_area("Cole o texto do documento", height=200)
    if st.button("Analisar"):
        if not texto_doc.strip():
            st.warning("Cole o texto do documento.")
        else:
            with st.spinner("Analisando com IA..."):
                try:
                    payload = {"tipo_documento": tipo_doc, "texto_bruto": texto_doc}
                    resp = requests.post(f"{API_BASE}/analisar-documento", json=payload, timeout=90)
                    if resp.status_code == 200:
                        dados = resp.json()
                        if dados.get("success"):
                            st.success("✅ Análise concluída!")
                            st.subheader("Dados Extraídos")
                            st.json(dados.get("dados_extraidos", {}))
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")

elif opcao == "Consulta Processo":
    st.header("📋 Consulta Processual (Simulada)")
    protocolo = st.text_input("Protocolo")
    nit_consulta = st.text_input("NIT (opcional)")
    if st.button("Consultar"):
        with st.spinner("Consultando..."):
            try:
                params = {}
                if protocolo:
                    params["protocolo"] = protocolo
                if nit_consulta:
                    params["nit"] = nit_consulta
                resp = requests.get(f"{API_BASE}/consultar-processo", params=params, timeout=60)
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("success"):
                        st.success("✅ Processo encontrado!")
                        st.write(f"**Status:** {dados.get('status')}")
                        for mov in dados.get("movimentacoes", []):
                            st.write(f"**{mov.get('data')}** - {mov.get('descricao')}")
                    else:
                        st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                else:
                    st.error(f"Erro HTTP {resp.status_code}")
            except Exception as e:
                st.error(f"Exceção: {e}")

elif opcao == "Auditoria de Processo":
    st.header("🩺 Auditoria de Processo")
    arquivos = st.file_uploader("Selecione os PDFs do processo", type=["pdf"], accept_multiple_files=True)
    if st.button("Processar Auditoria", disabled=not arquivos):
        with st.spinner("Processando..."):
            try:
                files = [("files", (arq.name, arq.getvalue(), "application/pdf")) for arq in arquivos]
                resp = requests.post(f"{API_BASE}/analisar-processo-completo", files=files, timeout=600)
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("success"):
                        st.success("✅ Auditoria concluída!")
                        # exibir KPI e abas (sua lógica anterior)
                    else:
                        st.error(f"Erro: {dados.get('error')}")
                else:
                    st.error(f"Erro HTTP {resp.status_code}")
            except Exception as e:
                st.error(f"Exceção: {e}")

elif opcao == "Extração de Dados com IA":
    st.header("🧠 Extração de Dados de Documentos Escaneados")
    st.markdown("Envie um PDF escaneado (RG, CPF, CTPS, CNIS) e a IA extrairá automaticamente os dados.")
    arquivo_extra = st.file_uploader("Escolha um PDF escaneado", type=["pdf"], key="extra_ia")
    if st.button("Extrair Dados", disabled=not arquivo_extra):
        with st.spinner("Extraindo dados com IA..."):
            try:
                files = {"file": (arquivo_extra.name, arquivo_extra.getvalue(), "application/pdf")}
                resp = requests.post(f"{API_BASE}/extrair-dados-ia", files=files, timeout=180)
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("success"):
                        st.success("✅ Extração concluída!")
                        extra = dados.get("dados", {})
                        st.write(f"**Nome:** {extra.get('nome', 'N/D')}")
                        st.write(f"**CPF:** {extra.get('cpf', 'N/D')}")
                        st.write(f"**NIT:** {extra.get('nit', 'N/D')}")
                        st.write(f"**Data de Nascimento:** {extra.get('data_nascimento', 'N/D')}")
                        st.write(f"**Nome da Mãe:** {extra.get('nome_mae', 'N/D')}")
                        st.write(f"**Sexo:** {extra.get('sexo', 'N/D')}")
                        if extra.get("vinculos"):
                            st.subheader("Vínculos Identificados")
                            for v in extra["vinculos"]:
                                st.write(f"- {v.get('empregador')} | {v.get('data_inicio')} a {v.get('data_fim')}")
                    else:
                        st.error(f"Erro: {dados.get('error')}")
                else:
                    st.error(f"Erro HTTP {resp.status_code}")
            except Exception as e:
                st.error(f"Exceção: {e}")
