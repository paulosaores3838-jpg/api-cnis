import streamlit as st
import requests
import json
import time

API_BASE = "https://api-cnis-4rxm.onrender.com"

st.set_page_config(page_title="Previdência Fácil - Análise Completa", layout="wide")

st.title("🛡️ Previdência Fácil - Análise Completa do Processo")
st.markdown("---")

st.markdown("""
### 📤 Envie todos os documentos do processo
Selecione **um ou mais PDFs** (CNIS, RG, CPF, laudos, PPP, carteira de trabalho, etc.).  
O sistema processará tudo e gerará um relatório unificado.
""")

arquivos = st.file_uploader("Escolha os PDFs do processo", type=["pdf"], accept_multiple_files=True)

if st.button("🚀 Analisar Tudo", disabled=not arquivos):
    if not arquivos:
        st.warning("Selecione pelo menos um PDF.")
    else:
        progresso = st.progress(0)
        status_texto = st.empty()

        try:
            files = []
            for arquivo in arquivos:
                files.append(("files", (arquivo.name, arquivo.getvalue(), "application/pdf")))

            status_texto.text("Enviando documentos...")
            resp = requests.post(f"{API_BASE}/analisar-processo-completo", files=files, timeout=120)
            progresso.progress(50)

            if resp.status_code == 200:
                dados = resp.json()
                progresso.progress(100)
                status_texto.text("Análise concluída!")
                time.sleep(0.5)
                progresso.empty()
                status_texto.empty()

                if not dados.get("success"):
                    st.error(f"Erro: {dados.get('error')}")
                else:
                    st.success("✅ Análise completa concluída!")
                    st.markdown("---")

                    # Dados pessoais
                    if dados.get("dados_pessoais"):
                        st.subheader("📋 Dados Pessoais")
                        pessoais = dados["dados_pessoais"]
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Nome:** {pessoais.get('nome', 'N/D')}")
                            st.write(f"**NIT:** {pessoais.get('nit', 'N/D')}")
                            st.write(f"**CPF:** {pessoais.get('cpf', 'N/D')}")
                        with col2:
                            st.write(f"**Data de Nascimento:** {pessoais.get('data_nascimento', 'N/D')}")
                            st.write(f"**Nome da Mãe:** {pessoais.get('nome_mae', 'N/D')}")
                        st.markdown("---")

                    # Vínculos
                    if dados.get("vinculos"):
                        st.subheader("Vínculos Empregatícios")
                        for v in dados["vinculos"]:
                            st.markdown(f"""
                            **Empregador:** {v.get('empregador', 'N/D')}  
                            **Data Início:** {v.get('data_inicio', 'N/D')} | **Data Fim:** {v.get('data_fim', 'N/D')}  
                            **Tipo Filiado:** {v.get('tipo_filiado', 'N/D')}  
                            **Última Remuneração:** {v.get('ultima_remuneracao', 'N/D')} | **Indicador:** {v.get('indicador', 'N/D')}
                            ---
                            """)
                        st.markdown("---")

                    # Cálculo
                    if dados.get("calculo") and dados["calculo"].get("success"):
                        st.subheader("🧮 Cálculo Previdenciário")
                        calc = dados["calculo"]
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Idade", calc.get("idade"))
                        col2.metric("Carência (meses)", calc.get("carencia_meses"))
                        col3.metric("Tempo de Contribuição", f"{calc.get('tempo_contribuicao_anos')}a {calc.get('tempo_contribuicao_meses')}m {calc.get('tempo_contribuicao_dias')}d")
                        st.markdown("**Simulações:**")
                        sim = calc.get("simulacao", {})
                        for chave, valor in sim.items():
                            elegivel = "🟢 Elegível" if valor.get("elegivel") else "🔴 Não Elegível"
                            st.write(f"**{chave.replace('_', ' ').title()}:** {elegivel}")
                        st.markdown("---")

                    # Auditoria
                    if dados.get("auditoria") and dados["auditoria"].get("success"):
                        st.subheader("🩺 Auditoria do Processo")
                        aud = dados["auditoria"]
                        st.write(f"**Status:** {aud.get('status_geral')}")
                        st.write(f"**Serviço detectado:** {aud.get('servico_detectado')}")
                        st.write(f"**Segurado:** {aud.get('segurado')}")
                        if aud.get("diagnostico_erros"):
                            st.markdown("### 🔴 Erros encontrados")
                            for erro in aud["diagnostico_erros"]:
                                st.markdown(f"""
                                **Local:** {erro.get('local_do_erro')}  
                                **Tipo:** {erro.get('tipo_de_erro')}  
                                **Descrição:** {erro.get('descricao')}  
                                **Como corrigir:** {erro.get('como_corrigir')}  
                                ---
                                """)
                        if aud.get("pontos_aprovados"):
                            st.markdown("### 🟢 Pontos aprovados")
                            for ponto in aud["pontos_aprovados"]:
                                st.write(f"✔️ {ponto}")
                        st.markdown("---")

                    # Documentos analisados
                    if dados.get("documentos_analisados"):
                        st.subheader("📎 Documentos analisados")
                        for doc in dados["documentos_analisados"]:
                            st.write(f"📄 {doc}")
            else:
                st.error(f"Erro HTTP {resp.status_code}")
        except Exception as e:
            st.error(f"Exceção: {e}")
