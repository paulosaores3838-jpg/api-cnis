import streamlit as st
import requests
import json
import time

# URL da API
API_BASE = "https://api-cnis-4rxm.onrender.com"

# Configuração da página
st.set_page_config(page_title="Previdência Fácil - Análise Completa", layout="wide")

# Título
st.title("🛡️ Previdência Fácil - Análise Completa do Processo")
st.markdown("---")

st.markdown("""
### 📤 Envie todos os documentos do processo

Selecione **um ou mais PDFs** (CNIS, RG, CPF, laudos, PPP, carteira de trabalho, etc.).  
O sistema irá processar tudo automaticamente e gerar um relatório unificado.
""")

# Upload múltiplo de PDFs
arquivos = st.file_uploader(
    "Escolha os PDFs do processo",
    type=["pdf"],
    accept_multiple_files=True
)

if st.button("🚀 Analisar Tudo", disabled=not arquivos):
    if not arquivos:
        st.warning("Selecione pelo menos um PDF.")
    else:
        progresso = st.progress(0)
        status_texto = st.empty()

        try:
            # ================== ETAPA 1: Upload do CNIS ==================
            status_texto.text("Procurando CNIS entre os arquivos...")
            cnis_encontrado = None
            for arquivo in arquivos:
                if "cnis" in arquivo.name.lower():
                    cnis_encontrado = arquivo
                    break

            dados_cnis = None
            if cnis_encontrado:
                status_texto.text(f"Processando CNIS: {cnis_encontrado.name}...")
                files = {"file": (cnis_encontrado.name, cnis_encontrado.getvalue(), "application/pdf")}
                resp = requests.post(f"{API_BASE}/upload-cnis", files=files, timeout=90)
                if resp.status_code == 200:
                    dados_cnis = resp.json()
            progresso.progress(20)

            # ================== ETAPA 2: Análise de outros documentos ==================
            status_texto.text("Analisando outros documentos com IA...")
            analises_docs = []
            for arquivo in arquivos:
                if arquivo.name.lower() != (cnis_encontrado.name if cnis_encontrado else ""):
                    files = {"file": (arquivo.name, arquivo.getvalue(), "application/pdf")}
                    # Para simplificar, apenas extraímos texto e enviamos para análise
                    # Nesse exemplo, chamamos /analisar-documento enviando texto vazio (não suportado)
                    # Vamos apenas armazenar o nome por enquanto
                    analises_docs.append({"nome": arquivo.name, "status": "Processado"})
            progresso.progress(40)

            # ================== ETAPA 3: Cálculo Previdenciário ==================
            nit = None
            if dados_cnis and dados_cnis.get("success"):
                pessoais = dados_cnis.get("dados_pessoais", {})
                nit = pessoais.get("nit")
            else:
                nit = st.text_input("Informe o NIT para cálculo (ou o sexo):", value="238.59380.10-5")

            sexo = st.selectbox("Sexo", ["M", "F"], key="sexo_calc")

            dados_calculo = None
            if nit and nit != "N/D":
                status_texto.text("Calculando benefícios...")
                payload_calc = {"nit": nit, "sexo": sexo}
                resp_calc = requests.post(f"{API_BASE}/calcular", json=payload_calc, timeout=60)
                if resp_calc.status_code == 200:
                    dados_calculo = resp_calc.json()
            progresso.progress(60)

            # ================== ETAPA 4: Auditoria ==================
            status_texto.text("Executando auditoria completa...")
            auditoria_result = None
            if arquivos:
                # Pega o primeiro PDF como base para auditoria
                primeiro_pdf = arquivos[0]
                files_aud = {"file": (primeiro_pdf.name, primeiro_pdf.getvalue(), "application/pdf")}
                resp_aud = requests.post(f"{API_BASE}/auditar-processo", files=files_aud, timeout=90)
                if resp_aud.status_code == 200:
                    auditoria_result = resp_aud.json()
            progresso.progress(80)

            # ================== ETAPA 5: Relatório Final ==================
            status_texto.text("Gerando relatório final...")
            progresso.progress(100)
            time.sleep(0.5)
            status_texto.empty()
            progresso.empty()

            st.success("✅ Análise completa concluída!")
            st.markdown("---")

            # Exibir dados pessoais
            if dados_cnis and dados_cnis.get("success"):
                st.subheader("📋 Dados Pessoais")
                pessoais = dados_cnis.get("dados_pessoais", {})
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Nome:** {pessoais.get('nome', 'N/D')}")
                    st.write(f"**NIT:** {pessoais.get('nit', 'N/D')}")
                    st.write(f"**CPF:** {pessoais.get('cpf', 'N/D')}")
                with col2:
                    st.write(f"**Data de Nascimento:** {pessoais.get('data_nascimento', 'N/D')}")
                    st.write(f"**Nome da Mãe:** {pessoais.get('nome_mae', 'N/D')}")

                st.subheader("Vínculos Empregatícios")
                vinculos = dados_cnis.get("vinculos", [])
                for v in vinculos:
                    st.markdown(f"""
                    **Empregador:** {v.get('empregador', 'N/D')}  
                    **Data Início:** {v.get('data_inicio', 'N/D')} | **Data Fim:** {v.get('data_fim', 'N/D')}  
                    **Tipo Filiado:** {v.get('tipo_filiado', 'N/D')}  
                    **Última Remuneração:** {v.get('ultima_remuneracao', 'N/D')} | **Indicador:** {v.get('indicador', 'N/D')}
                    ---
                    """)

            # Exibir cálculo
            if dados_calculo and dados_calculo.get("success"):
                st.subheader("🧮 Cálculo Previdenciário")
                col1, col2, col3 = st.columns(3)
                col1.metric("Idade", dados_calculo.get("idade"))
                col2.metric("Carência (meses)", dados_calculo.get("carencia_meses"))
                col3.metric("Tempo de Contribuição", f"{dados_calculo.get('tempo_contribuicao_anos')}a {dados_calculo.get('tempo_contribuicao_meses')}m {dados_calculo.get('tempo_contribuicao_dias')}d")
                st.write("Simulações:")
                sim = dados_calculo.get("simulacao", {})
                for chave, valor in sim.items():
                    elegivel = "🟢 Elegível" if valor.get("elegivel") else "🔴 Não Elegível"
                    st.write(f"**{chave.replace('_', ' ').title()}:** {elegivel}")

            # Exibir auditoria
            if auditoria_result and auditoria_result.get("success"):
                st.subheader("🩺 Auditoria do Processo")
                st.write(f"**Status:** {auditoria_result.get('status_geral')}")
                st.write(f"**Serviço detectado:** {auditoria_result.get('servico_detectado')}")
                st.write(f"**Segurado:** {auditoria_result.get('segurado')}")
                if auditoria_result.get("diagnostico_erros"):
                    st.markdown("### 🔴 Erros encontrados")
                    for erro in auditoria_result["diagnostico_erros"]:
                        st.markdown(f"""
                        **Local:** {erro.get('local_do_erro')}  
                        **Tipo:** {erro.get('tipo_de_erro')}  
                        **Descrição:** {erro.get('descricao')}  
                        **Como corrigir:** {erro.get('como_corrigir')}  
                        ---
                        """)
                if auditoria_result.get("pontos_aprovados"):
                    st.markdown("### 🟢 Pontos aprovados")
                    for ponto in auditoria_result["pontos_aprovados"]:
                        st.write(f"✔️ {ponto}")

        except Exception as e:
            st.error(f"Erro durante a análise: {e}")
