import streamlit as st
import requests
import json

# URL da API
API_BASE = "https://api-cnis-4rxm.onrender.com"

# Configuração da página
st.set_page_config(page_title="Previdência Fácil", layout="wide")

# Título
st.title("🛡️ Previdência Fácil - Assistente Previdenciário")
st.markdown("---")

# Menu lateral
opcao = st.sidebar.radio(
    "Selecione a funcionalidade:",
    ["Upload CNIS", "Calcular Benefício", "Analisar Documento", "Consulta Processo", "Auditoria de Processo"]
)

# ========== 1. UPLOAD CNIS ==========
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

                            # Dados pessoais
                            st.subheader("Dados Pessoais")
                            pessoais = dados.get("dados_pessoais", {})
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Nome:** {pessoais.get('nome', 'N/D')}")
                                st.write(f"**NIT:** {pessoais.get('nit', 'N/D')}")
                                st.write(f"**CPF:** {pessoais.get('cpf', 'N/D')}")
                            with col2:
                                st.write(f"**Data de Nascimento:** {pessoais.get('data_nascimento', 'N/D')}")
                                st.write(f"**Nome da Mãe:** {pessoais.get('nome_mae', 'N/D')}")

                            # Vínculos
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

# ========== 2. CALCULAR BENEFÍCIO ==========
elif opcao == "Calcular Benefício":
    st.header("🧮 Cálculo Previdenciário")
    nit = st.text_input("NIT do Segurado", placeholder="Ex: 238.59380.10-5")
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

                            st.subheader("Simulações de Aposentadoria")
                            sim = dados.get("simulacao", {})
                            for chave, valor in sim.items():
                                elegivel = "🟢 Elegível" if valor.get("elegivel") else "🔴 Não Elegível"
                                st.markdown(f"**{chave.replace('_', ' ').title()}:** {elegivel}")
                                st.write(valor)
                                st.divider()
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")

# ========== 3. ANALISAR DOCUMENTO ==========
elif opcao == "Analisar Documento":
    st.header("🔍 Análise de Documento com IA")
    tipo_doc = st.text_input("Tipo de Documento (ex: PPP, Laudo, Carteira)", value="PPP")
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
                            if dados.get("resumo"):
                                st.subheader("Resumo")
                                st.write(dados["resumo"])
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")

# ========== 4. CONSULTA PROCESSO ==========
elif opcao == "Consulta Processo":
    st.header("📋 Consulta Processual (Simulada)")
    protocolo = st.text_input("Protocolo", placeholder="Ex: 123456789")
    nit_consulta = st.text_input("NIT (opcional)", placeholder="Ex: 238.59380.10-5")

    if st.button("Consultar"):
        if not protocolo and not nit_consulta:
            st.warning("Informe protocolo ou NIT.")
        else:
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
                            st.subheader("Movimentações")
                            for mov in dados.get("movimentacoes", []):
                                st.write(f"**{mov.get('data')}** - {mov.get('descricao')}")
                            st.subheader("Documentos")
                            for doc in dados.get("documentos", []):
                                st.write(f"📎 {doc}")
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")

# ========== 5. AUDITORIA DE PROCESSO ==========
elif opcao == "Auditoria de Processo":
    st.header("🩺 Auditoria de Processo")
    arquivo = st.file_uploader("Envie o PDF do processo", type=["pdf"])

    if arquivo is not None:
        if st.button("Auditar"):
            with st.spinner("Analisando processo..."):
                try:
                    files = {"file": (arquivo.name, arquivo.getvalue(), "application/pdf")}
                    resp = requests.post(f"{API_BASE}/auditar-processo", files=files, timeout=90)
                    if resp.status_code == 200:
                        dados = resp.json()
                        if dados.get("success"):
                            st.success(f"Status: {dados.get('status_geral')}")
                            st.write(f"**Serviço detectado:** {dados.get('servico_detectado')}")
                            st.write(f"**Segurado:** {dados.get('segurado')}")

                            st.subheader("🔴 Erros encontrados")
                            for erro in dados.get("diagnostico_erros", []):
                                st.markdown(f"""
                                **Local:** {erro.get('local_do_erro')}  
                                **Tipo:** {erro.get('tipo_de_erro')}  
                                **Descrição:** {erro.get('descricao')}  
                                **Como corrigir:** {erro.get('como_corrigir')}  
                                ---
                                """)

                            st.subheader("🟢 Pontos aprovados")
                            for ponto in dados.get("pontos_aprovados", []):
                                st.write(f"✔️ {ponto}")
                        else:
                            st.error(f"Erro: {dados.get('error', 'Falha desconhecida')}")
                    else:
                        st.error(f"Erro HTTP {resp.status_code}")
                except Exception as e:
                    st.error(f"Exceção: {e}")
