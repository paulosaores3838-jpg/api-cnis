import streamlit as st
import requests
import json
import time
import pandas as pd

API_BASE = "https://api-cnis-4rxm.onrender.com"

# -------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA & ESTILO CUSTOMIZADO
# -------------------------------------------------------------
st.set_page_config(
    page_title="Previdência Fácil | Auditoria Inteligente",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        margin-bottom: 15px;
    }
    .badge-success {
        background-color: #dcfce7;
        color: #15803d;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.875rem;
        display: inline-block;
    }
    .badge-warning {
        background-color: #fef9c3;
        color: #a16207;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.875rem;
        display: inline-block;
    }
    .badge-danger {
        background-color: #fee2e2;
        color: #b91c1c;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.875rem;
        display: inline-block;
    }
    .audit-error-card {
        background-color: #fffaf0;
        border-left: 4px solid #dd6b20;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# BARRA LATERAL (SIDEBAR)
# -------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/942/942748.png", width=64)
    st.title("Previdência Fácil")
    st.caption("v2.4 • Auditoria & Diagnóstico INSS")
    st.markdown("---")

    st.markdown("### ⚙️ Status da Conexão")
    st.success("🟢 API Online (Render)")
    st.markdown(f"**Endpoint:** `{API_BASE}`")

    st.markdown("---")
    st.markdown("### 💡 Instruções")
    st.info("""
    1. Reúna os PDFs do processo (CNIS, RG, RGP, Laudos).
    2. Envie os arquivos no painel principal.
    3. O sistema roda a extração OCR, cálculo de tempo e auditoria preventiva.
    """)

# -------------------------------------------------------------
# CABEÇALHO PRINCIPAL
# -------------------------------------------------------------
st.title("⚖️ Painel de Auditoria Previdenciária")
st.markdown("Plataforma de pré-análise documental, contagem de tempo e conformidade normativa do INSS.")
st.markdown("---")

# -------------------------------------------------------------
# ÁREA DE UPLOAD E CONTROLE
# -------------------------------------------------------------
col_upload, col_action = st.columns([3, 1])

with col_upload:
    arquivos = st.file_uploader(
        "Selecione todos os PDFs do processo (CNIS, RG, RGP, Laudos, Formulários):",
        type=["pdf"],
        accept_multiple_files=True,
        help="Você pode selecionar múltiplos arquivos segurando Ctrl ou Shift."
    )

with col_action:
    st.write("##")
    btn_analisar = st.button(
        "🚀 Processar Auditoria",
        type="primary",
        use_container_width=True,
        disabled=not arquivos
    )

# -------------------------------------------------------------
# EXECUÇÃO DO PROCESSAMENTO
# -------------------------------------------------------------
if btn_analisar:
    progresso = st.progress(0)
    status_box = st.status("Processando processo completo...", expanded=True)

    try:
        status_box.write("📤 Enviando documentos para a API...")
        files = [("files", (arq.name, arq.getvalue(), "application/pdf")) for arq in arquivos]

        progresso.progress(25)
        status_box.write("🔍 Extraindo dados cadastrais e vínculos (OCR/Parsing)...")

        # Timeout aumentado para 300 segundos (5 minutos)
        resp = requests.post(f"{API_BASE}/analisar-processo-completo", files=files, timeout=300)
        progresso.progress(70)

        if resp.status_code == 200:
            dados = resp.json()
            progresso.progress(100)
            status_box.update(label="Auditoria Concluída com Sucesso!", state="complete", expanded=False)
            time.sleep(0.5)
            progresso.empty()

            if not dados.get("success"):
                st.error(f"❌ Falha no processamento: {dados.get('error')}")
            else:
                st.markdown("##")

                # ---------------------------------------------------------
                # RESUMO PRINCIPAL (KPI CARDS)
                # ---------------------------------------------------------
                pessoais = dados.get("dados_pessoais", {}) or {}
                aud = dados.get("auditoria", {}) or {}
                calc = dados.get("calculo", {}) or {}

                kpi1, kpi2, kpi3, kpi4 = st.columns(4)

                nome_completo = pessoais.get("nome") or "N/D"
                nome_exibicao = nome_completo[:18] + "..." if len(nome_completo) > 18 else nome_completo

                with kpi1:
                    st.metric(label="Titular do Processo", value=nome_exibicao)
                    st.caption(f"CPF: {pessoais.get('cpf', 'N/D')}")

                with kpi2:
                    st.metric(label="Serviço Identificado", value=aud.get("servico_detectado", "Geral / INSS"))
                    st.caption(f"NIT: {pessoais.get('nit', 'N/D')}")

                with kpi3:
                    tempo_anos = calc.get("tempo_contribuicao_anos")
                    tempo_meses = calc.get("tempo_contribuicao_meses")
                    tempo_dias = calc.get("tempo_contribuicao_dias")
                    if tempo_anos is not None:
                        tempo_exibicao = f"{tempo_anos}a {tempo_meses or 0}m {tempo_dias or 0}d"
                    else:
                        tempo_exibicao = "N/D"
                    st.metric(label="Tempo de Contribuição", value=tempo_exibicao)
                    st.caption(f"Carência: {calc.get('carencia_meses', 0)} meses")

                with kpi4:
                    status_geral = aud.get("status_geral", "Em Análise")
                    st.write("**Parecer da Auditoria**")
                    if "APROVA" in status_geral.upper() or "🟢" in status_geral:
                        st.markdown('<span class="badge-success">APTO PARA ENVIO</span>', unsafe_allow_html=True)
                    elif "RISCO" in status_geral.upper() or "🟡" in status_geral:
                        st.markdown('<span class="badge-warning">RISCO DE EXIGÊNCIA</span>', unsafe_allow_html=True)
                    else:
                        st.markdown('<span class="badge-danger">IMPEDIMENTO DETECTADO</span>', unsafe_allow_html=True)

                st.markdown("---")

                # ---------------------------------------------------------
                # NAVEGAÇÃO EM ABAS
                # ---------------------------------------------------------
                tab_auditoria, tab_calculos, tab_vinculos, tab_docs = st.tabs([
                    "🩺 Diagnóstico da Auditoria",
                    "🧮 Simulações de Benefício",
                    "💼 Vínculos & CNIS",
                    "📎 Documentos Analisados"
                ])

                # --- ABA 1: AUDITORIA ---
                with tab_auditoria:
                    col_erros, col_aprovados = st.columns([3, 2])

                    with col_erros:
                        st.subheader("🔴 Apontamentos e Pendências Detectadas")
                        erros = aud.get("diagnostico_erros", []) or []
                        if erros:
                            for idx, erro in enumerate(erros, 1):
                                tipo_erro = erro.get('tipo_de_erro', 'Inconsistência')
                                local_erro = erro.get('local_do_erro', 'Não informado')
                                descricao = erro.get('descricao', '')
                                como_corrigir = erro.get('como_corrigir', '')
                                st.markdown(f"""
                                <div class="audit-error-card">
                                    <h4 style="margin:0; color:#c05621;">#{idx} • {tipo_erro}</h4>
                                    <p style="margin:4px 0 8px 0; font-size:0.85rem; color:#718096;"><strong>Local:</strong> {local_erro}</p>
                                    <p style="margin:0 0 8px 0;">{descricao}</p>
                                    <div style="background:#fff; padding:10px; border-radius:6px; border:1px solid #fed7d7;">
                                        <strong>💡 Como Corrigir:</strong> {como_corrigir}
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.success("🎉 Nenhuma inconformidade impeditiva identificada no processo.")

                    with col_aprovados:
                        st.subheader("🟢 Itens em Conformidade")
                        aprovados = aud.get("pontos_aprovados", []) or []
                        if aprovados:
                            for ponto in aprovados:
                                st.markdown(f"✔️ **{ponto}**")
                        else:
                            st.info("Nenhum item pré-validado listado.")

                # --- ABA 2: CÁLCULOS ---
                with tab_calculos:
                    st.subheader("Regras de Transição & Elegibilidade (EC 103/2019)")
                    simulacoes = calc.get("simulacao", {}) or {}

                    if simulacoes:
                        chaves = list(simulacoes.keys())
                        cols = st.columns(len(chaves))
                        for col, chave in zip(cols, chaves):
                            res = simulacoes[chave]
                            elegivel = res.get("elegivel", False)
                            with col:
                                st.markdown(f"""
                                <div class="metric-card" style="text-align:center;">
                                    <p style="font-weight:600; margin-bottom:8px;">{chave.replace('_', ' ').title()}</p>
                                    {'<span class="badge-success">ELEGÍVEL</span>' if elegivel else '<span class="badge-danger">NÃO ELEGÍVEL</span>'}
                                </div>
                                """, unsafe_allow_html=True)
                    else:
                        st.info("Cálculo previdenciário não aplicável a este tipo de benefício.")

                # --- ABA 3: VÍNCULOS ---
                with tab_vinculos:
                    st.subheader("Histórico de Relações Previdenciárias")
                    vinculos = dados.get("vinculos", []) or []
                    if vinculos:
                        df_vinculos = pd.DataFrame(vinculos)
                        colunas_exibicao = {
                            "empregador": "Empregador / Origem",
                            "data_inicio": "Data Início",
                            "data_fim": "Data Fim",
                            "tipo_filiado": "Tipo Filiado",
                            "ultima_remuneracao": "Última Remuneração",
                            "indicador": "Indicadores"
                        }
                        # Renomeia apenas colunas existentes
                        renomear = {k: v for k, v in colunas_exibicao.items() if k in df_vinculos.columns}
                        df_vinculos = df_vinculos.rename(columns=renomear)
                        st.dataframe(df_vinculos, use_container_width=True, hide_index=True)
                    else:
                        st.warning("Nenhum vínculo empregatício encontrado ou extraído do CNIS.")

                # --- ABA 4: DOCUMENTOS ANALISADOS ---
                with tab_docs:
                    st.subheader("Arquivos Processados neste Lote")
                    docs = dados.get("documentos_analisados", []) or []
                    if docs:
                        for doc in docs:
                            st.markdown(f"📄 **{doc}**")
                    else:
                        st.info("Nenhum documento analisado.")

        else:
            status_box.update(label=f"Erro HTTP {resp.status_code}", state="error")
            st.error(f"Erro ao conectar com a API: Código {resp.status_code}")

    except requests.exceptions.Timeout:
        st.error("⏳ Tempo limite excedido. Os PDFs enviados são muito pesados para o processamento síncrono. Tente enviar menos arquivos ou arquivos menores.")
    except Exception as e:
        st.error(f"⚠️ Ocorreu uma exceção inesperada: {e}")
