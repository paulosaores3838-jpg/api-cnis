from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import pdfplumber
import re
import tempfile
import os
import json
from datetime import datetime, date
from supabase import create_client, Client
import pytesseract
from PIL import Image
import pymupdf  # PyMuPDF
import requests

app = FastAPI(title="API Previdenciária Completa", version="1.5.0")

# ========== CONFIGURAÇÃO ==========
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-flash-latest")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")

# ========== MODELOS ==========
class Vinculo(BaseModel):
    sequencia: Optional[str] = None
    nit: Optional[str] = None
    codigo_empregador: Optional[str] = None
    empregador: Optional[str] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    tipo_filiado: Optional[str] = None
    ultima_remuneracao: Optional[str] = None
    indicador: Optional[str] = None

class DadosPessoais(BaseModel):
    nome: Optional[str] = None
    nit: Optional[str] = None
    cpf: Optional[str] = None
    data_nascimento: Optional[str] = None
    nome_mae: Optional[str] = None
    sexo: Optional[str] = None

class DadosExtraidosIA(BaseModel):
    nome: Optional[str] = None
    cpf: Optional[str] = None
    nit: Optional[str] = None
    data_nascimento: Optional[str] = None
    nome_mae: Optional[str] = None
    sexo: Optional[str] = None
    vinculos: List[Vinculo] = []
    observacoes: Optional[str] = None

class ExtracaoIAResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    dados: Optional[DadosExtraidosIA] = None
    texto_bruto: Optional[str] = None

class CnisResponse(BaseModel):
    filename: str
    success: bool
    dados_pessoais: Optional[DadosPessoais] = None
    vinculos: List[Vinculo] = []
    error: Optional[str] = None
    saved: bool = False
    segurado_id: Optional[str] = None

class CalcularRequest(BaseModel):
    nit: str
    sexo: Optional[str] = None

class CalculoResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    idade: Optional[int] = None
    tempo_contribuicao_anos: Optional[int] = None
    tempo_contribuicao_meses: Optional[int] = None
    tempo_contribuicao_dias: Optional[int] = None
    carencia_meses: Optional[int] = None
    simulacao: Optional[Dict[str, Any]] = None

class DocumentoAnaliseRequest(BaseModel):
    nit: Optional[str] = None
    tipo_documento: Optional[str] = None
    texto_bruto: Optional[str] = None

class DocumentoAnaliseResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    dados_extraidos: Optional[Dict[str, Any]] = None
    resumo: Optional[str] = None

class ProcessoConsultaResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    protocolo: Optional[str] = None
    status: Optional[str] = None
    movimentacoes: Optional[List[Dict[str, str]]] = None
    documentos: Optional[List[str]] = None

class ErroDiagnostico(BaseModel):
    local_do_erro: Optional[str] = None
    tipo_de_erro: Optional[str] = None
    descricao: Optional[str] = None
    como_corrigir: Optional[str] = None

class AuditoriaResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    status_geral: Optional[str] = None
    servico_detectado: Optional[str] = None
    segurado: Optional[str] = None
    diagnostico_erros: List[ErroDiagnostico] = []
    pontos_aprovados: List[str] = []

class ProcessoCompletoResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    dados_pessoais: Optional[DadosPessoais] = None
    vinculos: List[Vinculo] = []
    calculo: Optional[CalculoResponse] = None
    auditoria: Optional[AuditoriaResponse] = None
    documentos_analisados: List[str] = []

# ========== FUNÇÕES AUXILIARES ==========
def extrair_texto_pdf(caminho_arquivo):
    texto = ""
    with pdfplumber.open(caminho_arquivo) as pdf:
        for pagina in pdf.pages:
            conteudo = pagina.extract_text()
            if conteudo:
                texto += conteudo + "\n"
    return texto.strip()

def extrair_texto_pdf_ocr(caminho_arquivo):
    texto = ""
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    doc = pymupdf.open(caminho_arquivo)
    total_paginas = min(10, len(doc))
    for page_num in range(total_paginas):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=150)
        img_path = f"temp_page_{page_num}.png"
        pix.save(img_path)
        img = Image.open(img_path)
        texto += pytesseract.image_to_string(img, lang="por") + "\n"
        os.remove(img_path)
    doc.close()
    return texto.strip()

def extrair_dados_pessoais(texto):
    dados = DadosPessoais()
    m = re.search(r'NIT:\s*(\d{3}\.\d{5}\.\d{2}-\d)', texto)
    if m:
        dados.nit = m.group(1)
    m = re.search(r'CPF:\s*(\d{3}\.\d{3}\.\d{3}-\d{2})', texto)
    if m:
        dados.cpf = m.group(1)
    m = re.search(r'Nome:\s*(.*)', texto)
    if m:
        dados.nome = m.group(1).strip()
    m = re.search(r'Data de nascimento:\s*(\d{2}/\d{2}/\d{4})', texto)
    if m:
        dados.data_nascimento = m.group(1)
    m = re.search(r'Nome da mãe:\s*(.*)', texto)
    if m:
        dados.nome_mae = m.group(1).strip()
    return dados

def parsear_vinculos_cnis(texto):
    linhas = texto.split('\n')
    vinculos = []
    i = 0
    padrao_inicio = re.compile(r'^\s*\d+\s+\d{3}\.\d{5}\.\d{2}-\d')

    while i < len(linhas):
        linha = linhas[i].strip()
        if not linha:
            i += 1
            continue

        if padrao_inicio.match(linha):
            tipo_filiado = ""
            if i > 0:
                anterior = linhas[i-1].strip()
                if "Empregado" in anterior or "Agente" in anterior:
                    tipo_filiado = anterior + " "

            partes = linha.split()
            if len(partes) >= 10:
                sequencia = partes[0]
                nit = partes[1]
                codigo_empregador = partes[2]

                padrao_data = re.compile(r'\d{2}/\d{2}/\d{4}')
                datas = padrao_data.findall(linha)
                if len(datas) >= 2:
                    data_inicio = datas[0]
                    data_fim = datas[1]
                else:
                    data_inicio = data_fim = ""

                match_emp = re.search(rf'{codigo_empregador}\s+(.*?)\s+{data_inicio}', linha)
                empregador = match_emp.group(1).strip() if match_emp else "Não identificado"

                resto = linha.split(data_fim)[-1].strip() if data_fim else ""
                match_resto = re.search(r'(\d{2}/\d{4})\s+(\S+)', resto)
                ultima_remuneracao = match_resto.group(1) if match_resto else ""
                indicador = match_resto.group(2) if match_resto else resto

                if i+1 < len(linhas):
                    proxima = linhas[i+1].strip()
                    if "Agente" in proxima:
                        tipo_filiado += proxima
                        i += 1

                vinculos.append(Vinculo(
                    sequencia=sequencia,
                    nit=nit,
                    codigo_empregador=codigo_empregador,
                    empregador=empregador,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                    tipo_filiado=tipo_filiado.strip(),
                    ultima_remuneracao=ultima_remuneracao,
                    indicador=indicador
                ))
        i += 1
    return vinculos

def parse_data(data_str):
    try:
        return datetime.strptime(data_str, "%d/%m/%Y").date()
    except:
        return None

def calcular_tempo(vinculos):
    total_dias = 0
    for v in vinculos:
        if not v.data_inicio:
            continue
        di = parse_data(v.data_inicio)
        if not di:
            continue
        if v.data_fim:
            df = parse_data(v.data_fim)
        else:
            df = date.today()
        if not df or df < di:
            continue
        dias = (df - di).days + 1
        total_dias += dias
    anos = total_dias // 365
    meses = (total_dias % 365) // 30
    dias_rest = (total_dias % 365) % 30
    return total_dias, anos, meses, dias_rest

def calcular_carencia(vinculos):
    meses_set = set()
    for v in vinculos:
        if not v.data_inicio:
            continue
        di = parse_data(v.data_inicio)
        if not di:
            continue
        if v.data_fim:
            df = parse_data(v.data_fim)
        else:
            df = date.today()
        if not df or df < di:
            continue
        cursor = di
        while cursor <= df:
            meses_set.add((cursor.year, cursor.month))
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year+1, month=1, day=1)
            else:
                cursor = cursor.replace(month=cursor.month+1, day=1)
    return len(meses_set)

def calcular_idade(data_nascimento):
    if not data_nascimento:
        return None
    d = parse_data(data_nascimento)
    if not d:
        return None
    hoje = date.today()
    idade = hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))
    return idade

def calcular_tempo_especial(vinculos):
    tempo_especial_dias = 0
    for v in vinculos:
        if v.indicador and ("ESPECIAL" in v.indicador.upper() or "INDPEND" in v.indicador.upper()):
            if v.data_inicio:
                di = parse_data(v.data_inicio)
                df = parse_data(v.data_fim) if v.data_fim else date.today()
                if di and df:
                    tempo_especial_dias += (df - di).days + 1
    anos = tempo_especial_dias // 365
    meses = (tempo_especial_dias % 365) // 30
    dias = (tempo_especial_dias % 365) % 30
    return anos, meses, dias

def simular_aposentadorias(idade, tempo_anos_total, carencia_meses, sexo):
    sim = {}
    idade_minima = 65 if sexo == "M" else 62
    sim["aposentadoria_idade"] = {
        "idade_atual": idade,
        "idade_necessaria": idade_minima,
        "carencia_atual": carencia_meses,
        "carencia_necessaria": 180,
        "elegivel": (idade >= idade_minima and carencia_meses >= 180)
    }
    tempo_necessario = 35 if sexo == "M" else 30
    sim["aposentadoria_tempo"] = {
        "tempo_atual_anos": round(tempo_anos_total, 2),
        "tempo_necessario": tempo_necessario,
        "elegivel": (tempo_anos_total >= tempo_necessario)
    }
    pontos_necessarios = 101 if sexo == "M" else 91
    pontos_atuais = idade + tempo_anos_total
    sim["aposentadoria_pontos"] = {
        "pontos_atuais": round(pontos_atuais, 1),
        "pontos_necessarios": pontos_necessarios,
        "elegivel": (pontos_atuais >= pontos_necessarios)
    }
    pedagio_necessario = 35 if sexo == "M" else 30
    sim["aposentadoria_pedagio_50"] = {
        "tempo_necessario": pedagio_necessario,
        "tempo_atual": round(tempo_anos_total, 2),
        "elegivel": (tempo_anos_total >= pedagio_necessario)
    }
    return sim

def analisar_texto_com_ia(texto: str, tipo_documento: str) -> Dict[str, Any]:
    if not LLM_API_KEY:
        return {"erro": "Chave de API de IA não configurada."}
    try:
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        Você é um assistente especializado em direito previdenciário brasileiro.
        Analise o seguinte documento ({tipo_documento}) e extraia os dados relevantes em formato JSON.
        Documento:
        {texto[:3000]}
        Retorne apenas JSON válido.
        """
        payload = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        response = requests.post(
            f"{LLM_API_BASE.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except:
                return {"resumo": content}
        else:
            return {"erro": f"Falha na API: {response.status_code}"}
    except Exception as e:
        return {"erro": str(e)}

def extrair_dados_auditoria_ia(texto: str) -> Dict[str, Any]:
    if not LLM_API_KEY:
        return {"erro": "Chave de API de IA não configurada."}
    try:
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        Você é um auditor previdenciário sênior. Analise o texto abaixo e retorne um JSON com:
        - tipo_servico: um dos valores: SEGURO_DEFESO, APOSENTADORIA, AUXILIO_INCAPACIDADE, BPC_LOAS, PENSAO_MORTE, OUTRO
        - segurado: nome do segurado
        - dados_especificos: um dicionário com os campos mais relevantes para o tipo de serviço identificado.
        Exemplos de campos por serviço:
        SEGURO_DEFESO: rgp_data_emissao, rgp_ativo, possui_vinculo_clt, possui_mei, recebe_outro_beneficio, portaria_defeso_vigente
        APOSENTADORIA: vinculos, tempo_contribuicao_anos, carencia_meses, idade, sexo, indicadores_pendentes
        AUXILIO_INCAPACIDADE: dii, qualidade_segurado, carencia_meses, laudo_cid, crm_assinatura
        BPC_LOAS: cadunico_atualizado, renda_per_capita, idade, comprovacao_deficiencia
        PENSAO_MORTE: qualidade_segurado_obito, relacao_dependencia, data_obito
        Texto:
        {texto[:3000]}
        Retorne APENAS JSON válido, sem texto adicional.
        """
        payload = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        response = requests.post(
            f"{LLM_API_BASE.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except:
                content_clean = content.strip("`").replace("json", "", 1).strip()
                return json.loads(content_clean)
        else:
            return {"erro": f"Falha na API: {response.status_code}"}
    except Exception as e:
        return {"erro": str(e)}

def extrair_dados_com_ia(texto: str) -> DadosExtraidosIA:
    if not LLM_API_KEY:
        return DadosExtraidosIA(observacoes="Chave de IA não configurada.")
    try:
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        Você é um assistente especializado em análise de documentos pessoais brasileiros (RG, CPF, CTPS, CNIS).
        Extraia do texto abaixo os seguintes campos, se presentes, e retorne APENAS JSON válido:
        {{
          "nome": "string",
          "cpf": "string",
          "nit": "string",
          "data_nascimento": "dd/mm/aaaa",
          "nome_mae": "string",
          "sexo": "M ou F",
          "vinculos": [
            {{
              "empregador": "string",
              "data_inicio": "dd/mm/aaaa",
              "data_fim": "dd/mm/aaaa",
              "cargo": "string",
              "remuneracao": "string"
            }}
          ]
        }}
        Se algum campo não for encontrado, use null.
        Texto:
        {texto[:5000]}
        """
        payload = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        response = requests.post(
            f"{LLM_API_BASE.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            content = content.strip("`").replace("json", "", 1).strip()
            dados_dict = json.loads(content)
            vinculos = []
            for v in dados_dict.get("vinculos", []):
                vinculos.append(Vinculo(
                    empregador=v.get("empregador"),
                    data_inicio=v.get("data_inicio"),
                    data_fim=v.get("data_fim"),
                    ultima_remuneracao=v.get("remuneracao"),
                    tipo_filiado=v.get("cargo")
                ))
            return DadosExtraidosIA(
                nome=dados_dict.get("nome"),
                cpf=dados_dict.get("cpf"),
                nit=dados_dict.get("nit"),
                data_nascimento=dados_dict.get("data_nascimento"),
                nome_mae=dados_dict.get("nome_mae"),
                sexo=dados_dict.get("sexo"),
                vinculos=vinculos,
                observacoes="Extração realizada por IA."
            )
        else:
            return DadosExtraidosIA(observacoes=f"Erro na API: {response.status_code}")
    except Exception as e:
        return DadosExtraidosIA(observacoes=f"Erro: {e}")

# ========== MOTORES DE REGRAS ==========
def motor_seguro_defeso(dados: Dict[str, Any]) -> AuditoriaResponse:
    erros = []
    aprovados = []
    rgp_data = dados.get("rgp_data_emissao")
    rgp_ativo = dados.get("rgp_ativo")
    possui_vinculo = dados.get("possui_vinculo_clt")
    possui_mei = dados.get("possui_mei")
    recebe_beneficio = dados.get("recebe_outro_beneficio")
    portaria = dados.get("portaria_defeso_vigente")

    if rgp_ativo == False:
        erros.append(ErroDiagnostico(local_do_erro="RGP", tipo_de_erro="RGP inativo ou vencido", descricao="O RGP não está ativo.", como_corrigir="Solicite a regularização do RGP junto ao MPA."))
    if rgp_data:
        data_emissao = parse_data(rgp_data)
        if data_emissao:
            hoje = date.today()
            if (hoje - data_emissao).days < 365:
                erros.append(ErroDiagnostico(local_do_erro="RGP", tipo_de_erro="RGP emitido há menos de 12 meses", descricao="O RGP foi emitido recentemente.", como_corrigir="Se possuir RGP antigo, anexe o histórico. Caso contrário, o pedido será indeferido."))
        else:
            erros.append(ErroDiagnostico(local_do_erro="RGP", tipo_de_erro="Data de emissão do RGP não identificada", descricao="Não foi possível identificar a data de emissão do RGP.", como_corrigir="Anexe o RGP legível ou histórico atualizado."))
    else:
        erros.append(ErroDiagnostico(local_do_erro="RGP", tipo_de_erro="RGP não informado", descricao="Não foi possível identificar o RGP.", como_corrigir="Anexe o RGP ou histórico do MPA."))

    if possui_vinculo == True:
        erros.append(ErroDiagnostico(local_do_erro="CNIS", tipo_de_erro="Vínculo CLT ativo", descricao="Existe vínculo CLT ativo, incompatível com o defeso.", como_corrigir="Verifique se o vínculo já foi encerrado; se não, solicite acerto de vínculo no Meu INSS."))
    if possui_mei == True:
        erros.append(ErroDiagnostico(local_do_erro="CPF/CNPJ", tipo_de_erro="Pescador possui MEI/CNPJ ativo", descricao="Pescador com MEI ativo pode ser considerado empresário e não elegível.", como_corrigir="Comprove que a atividade é exclusivamente artesanal ou encerre o MEI."))
    if recebe_beneficio == True:
        erros.append(ErroDiagnostico(local_do_erro="Benefícios", tipo_de_erro="Acúmulo de benefício incompatível", descricao="Recebimento de outro benefício pode bloquear o defeso.", como_corrigir="Verifique a compatibilidade do benefício com o defeso."))
    if portaria == False:
        erros.append(ErroDiagnostico(local_do_erro="Portaria", tipo_de_erro="Defeso não vigente", descricao="A portaria do defeso não está vigente para o período.", como_corrigir="Confirme o período de defeso no site do MPA."))
    if not erros:
        aprovados.append("RGP ativo e com mais de 12 meses")
        aprovados.append("Sem vínculos incompatíveis")
        aprovados.append("Defeso vigente")

    status = "✅ APROVADO" if not erros else "🟡 RISCO DE INDEFERIMENTO"
    return AuditoriaResponse(
        success=True,
        status_geral=status,
        servico_detectado="Seguro-Defeso (SDPA)",
        segurado=dados.get("segurado", "Não identificado"),
        diagnostico_erros=erros,
        pontos_aprovados=aprovados
    )

def motor_aposentadoria(dados: Dict[str, Any]) -> AuditoriaResponse:
    erros = []
    aprovados = []
    indicadores = dados.get("indicadores_pendentes", [])
    if indicadores:
        erros.append(ErroDiagnostico(local_do_erro="CNIS", tipo_de_erro="Indicadores de pendência", descricao=f"Indicadores pendentes: {indicadores}", como_corrigir="Anexe documentos para regularizar."))
    tempo = float(dados.get("tempo_contribuicao_anos", 0) or 0)
    carencia = int(dados.get("carencia_meses", 0) or 0)
    sexo = dados.get("sexo", "M")
    idade = int(dados.get("idade", 0) or 0)
    if carencia < 180:
        erros.append(ErroDiagnostico(local_do_erro="Carência", tipo_de_erro="Carência insuficiente", descricao=f"Carência de {carencia} meses, menor que 180.", como_corrigir="Aguarde completar 180 meses ou verifique períodos não computados."))
    tempo_necessario = 35 if sexo == "M" else 30
    if tempo < tempo_necessario:
        erros.append(ErroDiagnostico(local_do_erro="Tempo de contribuição", tipo_de_erro="Tempo abaixo do necessário", descricao=f"Tempo de contribuição de {tempo} anos, abaixo de {tempo_necessario}.", como_corrigir="Verifique vínculos não baixados ou averbação de tempo especial."))
    if not erros:
        aprovados.append("Carência e tempo de contribuição atingidos")
    status = "✅ APROVADO" if not erros else "🟡 RISCO DE INDEFERIMENTO"
    return AuditoriaResponse(
        success=True,
        status_geral=status,
        servico_detectado="Aposentadoria",
        segurado=dados.get("segurado", "Não identificado"),
        diagnostico_erros=erros,
        pontos_aprovados=aprovados
    )

def motor_auxilio_incapacidade(dados: Dict[str, Any]) -> AuditoriaResponse:
    erros = []
    aprovados = []
    qualidade = dados.get("qualidade_segurado")
    carencia = int(dados.get("carencia_meses", 0) or 0)
    dii = dados.get("dii")
    laudo_cid = dados.get("laudo_cid")
    crm = dados.get("crm_assinatura")
    if qualidade == False:
        erros.append(ErroDiagnostico(local_do_erro="Qualidade de segurado", tipo_de_erro="Perda da qualidade de segurado", descricao="Não há qualidade de segurado na DII.", como_corrigir="Comprove que a doença começou antes da perda da qualidade."))
    if carencia < 12:
        erros.append(ErroDiagnostico(local_do_erro="Carência", tipo_de_erro="Carência insuficiente", descricao=f"Carência de {carencia} meses, menor que 12.", como_corrigir="Verifique se há isenção de carência para a patologia."))
    if not laudo_cid:
        erros.append(ErroDiagnostico(local_do_erro="Laudo médico", tipo_de_erro="CID não informado", descricao="O laudo não contém o CID.", como_corrigir="Solicite ao médico laudo com CID."))
    if not crm:
        erros.append(ErroDiagnostico(local_do_erro="Laudo médico", tipo_de_erro="Assinatura/CRM ilegível", descricao="CRM ou assinatura não identificados.", como_corrigir="Anexe laudo legível com CRM e assinatura."))
    if not erros:
        aprovados.append("Laudo completo e carência cumprida")
    status = "✅ APROVADO" if not erros else "🟡 RISCO DE INDEFERIMENTO"
    return AuditoriaResponse(
        success=True,
        status_geral=status,
        servico_detectado="Auxílio-Doença / Incapacidade",
        segurado=dados.get("segurado", "Não identificado"),
        diagnostico_erros=erros,
        pontos_aprovados=aprovados
    )

def motor_bpc_loas(dados: Dict[str, Any]) -> AuditoriaResponse:
    erros = []
    aprovados = []
    cadunico = dados.get("cadunico_atualizado")
    renda = float(dados.get("renda_per_capita", 0) or 0)
    comprovacao_deficiencia = dados.get("comprovacao_deficiencia")
    if cadunico == False:
        erros.append(ErroDiagnostico(local_do_erro="CadÚnico", tipo_de_erro="CadÚnico desatualizado", descricao="Cadastro desatualizado há mais de 2 anos.", como_corrigir="Atualize o CadÚnico no CRAS antes de protocolar."))
    if renda > 0.25:
        erros.append(ErroDiagnostico(local_do_erro="Renda familiar", tipo_de_erro="Renda per capita acima de 1/4 do salário mínimo", descricao=f"Renda per capita de {renda} salários mínimos.", como_corrigir="Verifique se há despesas dedutíveis ou membros não considerados."))
    if comprovacao_deficiencia == False:
        erros.append(ErroDiagnostico(local_do_erro="Deficiência", tipo_de_erro="Impedimento de longo prazo não comprovado", descricao="Laudos insuficientes para PCD.", como_corrigir="Anexe laudos médicos e exames atualizados."))
    if not erros:
        aprovados.append("Critérios de renda e cadastro atendidos")
    status = "✅ APROVADO" if not erros else "🟡 RISCO DE INDEFERIMENTO"
    return AuditoriaResponse(
        success=True,
        status_geral=status,
        servico_detectado="BPC/LOAS",
        segurado=dados.get("segurado", "Não identificado"),
        diagnostico_erros=erros,
        pontos_aprovados=aprovados
    )

def motor_pensao_morte(dados: Dict[str, Any]) -> AuditoriaResponse:
    erros = []
    aprovados = []
    qualidade_obito = dados.get("qualidade_segurado_obito")
    relacao = dados.get("relacao_dependencia")
    data_obito = dados.get("data_obito")
    if qualidade_obito == False:
        erros.append(ErroDiagnostico(local_do_erro="Qualidade de segurado do falecido", tipo_de_erro="Falecido sem qualidade de segurado", descricao="O falecido não tinha qualidade de segurado na data do óbito.", como_corrigir="Comprove contribuições ou manutenção da qualidade."))
    if not relacao:
        erros.append(ErroDiagnostico(local_do_erro="Dependência", tipo_de_erro="Dependência não comprovada", descricao="Não foi possível comprovar dependência.", como_corrigir="Anexe documentos que comprovem dependência econômica."))
    if not data_obito:
        erros.append(ErroDiagnostico(local_do_erro="Certidão de óbito", tipo_de_erro="Data de óbito não informada", descricao="Data de óbito não identificada.", como_corrigir="Anexe certidão de óbito legível."))
    if not erros:
        aprovados.append("Dependência e qualidade de segurado confirmadas")
    status = "✅ APROVADO" if not erros else "🟡 RISCO DE INDEFERIMENTO"
    return AuditoriaResponse(
        success=True,
        status_geral=status,
        servico_detectado="Pensão por Morte",
        segurado=dados.get("segurado", "Não identificado"),
        diagnostico_erros=erros,
        pontos_aprovados=aprovados
    )

def roteador_auditoria(dados_ia: Dict[str, Any]) -> AuditoriaResponse:
    tipo = dados_ia.get("tipo_servico", "OUTRO").upper()
    segurado = dados_ia.get("segurado", "Não identificado")
    especificos = dados_ia.get("dados_especificos", {}) or {}

    if tipo == "SEGURO_DEFESO":
        return motor_seguro_defeso(especificos)
    elif tipo == "APOSENTADORIA":
        return motor_aposentadoria(especificos)
    elif tipo == "AUXILIO_INCAPACIDADE":
        return motor_auxilio_incapacidade(especificos)
    elif tipo == "BPC_LOAS":
        return motor_bpc_loas(especificos)
    elif tipo == "PENSAO_MORTE":
        return motor_pensao_morte(especificos)
    else:
        return AuditoriaResponse(
            success=True,
            status_geral="⚠️ NÃO FOI POSSÍVEL IDENTIFICAR O TIPO DE BENEFÍCIO",
            servico_detectado="Desconhecido",
            segurado=segurado,
            diagnostico_erros=[ErroDiagnostico(local_do_erro="Identificação", tipo_de_erro="Benefício não identificado", descricao="Não foi possível classificar o serviço.", como_corrigir="Verifique se o documento contém informações suficientes.")],
            pontos_aprovados=[]
        )

# ========== ENDPOINTS ==========
@app.post("/upload-cnis", response_model=CnisResponse)
async def upload_cnis(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas PDF")

    conteudo = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(conteudo)
        caminho = tmp.name

    try:
        texto = extrair_texto_pdf(caminho)
        if not texto:
            texto = extrair_texto_pdf_ocr(caminho)
        if not texto:
            return CnisResponse(
                filename=file.filename,
                success=False,
                error="Não foi possível extrair texto do PDF (mesmo com OCR)."
            )

        dados_pessoais = extrair_dados_pessoais(texto)
        vinculos = parsear_vinculos_cnis(texto)

        saved = False
        segurado_id = None

        if supabase:
            try:
                response_seg = supabase.table("segurados").upsert(
                    {
                        "nome": dados_pessoais.nome,
                        "nit": dados_pessoais.nit,
                        "cpf": dados_pessoais.cpf,
                        "data_nascimento": dados_pessoais.data_nascimento,
                        "nome_mae": dados_pessoais.nome_mae,
                    },
                    on_conflict="nit"
                ).execute()
                if response_seg.data:
                    segurado_id = response_seg.data[0]["id"]
                saved = True
                if dados_pessoais.nit:
                    supabase.table("vinculos").delete().eq("nit", dados_pessoais.nit).execute()
                for v in vinculos:
                    supabase.table("vinculos").insert({
                        "filename": file.filename,
                        "sequencia": v.sequencia,
                        "nit": v.nit,
                        "codigo_empregador": v.codigo_empregador,
                        "empregador": v.empregador,
                        "data_inicio": v.data_inicio,
                        "data_fim": v.data_fim,
                        "tipo_filiado": v.tipo_filiado,
                        "ultima_remuneracao": v.ultima_remuneracao,
                        "indicador": v.indicador
                    }).execute()
            except Exception as e:
                print(f"Erro ao salvar no Supabase: {e}")

        return CnisResponse(
            filename=file.filename,
            success=True,
            dados_pessoais=dados_pessoais,
            vinculos=vinculos,
            saved=saved,
            segurado_id=segurado_id
        )
    except Exception as e:
        return CnisResponse(
            filename=file.filename,
            success=False,
            error=f"Erro: {str(e)}"
        )
    finally:
        if os.path.exists(caminho):
            os.unlink(caminho)

@app.post("/calcular", response_model=CalculoResponse)
async def calcular(request: CalcularRequest):
    if not supabase:
        return CalculoResponse(success=False, error="Supabase não configurado")

    nit = request.nit.strip()
    if not nit:
        return CalculoResponse(success=False, error="NIT é obrigatório")

    try:
        response_seg = supabase.table("segurados").select("*").eq("nit", nit).execute()
        if not response_seg.data:
            return CalculoResponse(success=False, error="Segurado não encontrado")

        segurado = response_seg.data[0]
        sexo = request.sexo or segurado.get("sexo")
        if not sexo or sexo not in ("M", "F"):
            return CalculoResponse(success=False, error="Sexo não informado. Informe 'M' ou 'F' no corpo da requisição ou atualize o cadastro do segurado.")

        response_vin = supabase.table("vinculos").select("*").eq("nit", nit).execute()
        vinculos_data = response_vin.data or []
        lista_vinculos = [Vinculo(**v) for v in vinculos_data if v.get("data_inicio")]

        idade = calcular_idade(segurado.get("data_nascimento"))
        total_dias, anos, meses, dias = calcular_tempo(lista_vinculos)
        carencia = calcular_carencia(lista_vinculos)

        tempo_anos_total = anos + (meses / 12) + (dias / 365)
        simulacao = simular_aposentadorias(idade, tempo_anos_total, carencia, sexo)

        return CalculoResponse(
            success=True,
            idade=idade,
            tempo_contribuicao_anos=anos,
            tempo_contribuicao_meses=meses,
            tempo_contribuicao_dias=dias,
            carencia_meses=carencia,
            simulacao=simulacao
        )
    except Exception as e:
        return CalculoResponse(success=False, error=f"Erro ao calcular: {str(e)}")

@app.post("/analisar-documento", response_model=DocumentoAnaliseResponse)
async def analisar_documento(request: DocumentoAnaliseRequest):
    if not request.texto_bruto:
        return DocumentoAnaliseResponse(success=False, error="texto_bruto é obrigatório")

    resultado_ia = analisar_texto_com_ia(request.texto_bruto, request.tipo_documento or "documento")

    return DocumentoAnaliseResponse(
        success=True,
        dados_extraidos=resultado_ia,
        resumo=resultado_ia.get("resumo", "")
    )

@app.get("/consultar-processo", response_model=ProcessoConsultaResponse)
async def consultar_processo(protocolo: str = None, nit: str = None):
    if not protocolo and not nit:
        return ProcessoConsultaResponse(success=False, error="Informe protocolo ou NIT")

    return ProcessoConsultaResponse(
        success=True,
        protocolo=protocolo or "S/N",
        status="EM ANÁLISE",
        movimentacoes=[
            {"data": "10/08/2026", "descricao": "Requerimento protocolado"},
            {"data": "12/08/2026", "descricao": "Documentos anexados"},
            {"data": "13/08/2026", "descricao": "Em análise pelo INSS"}
        ],
        documentos=["Requerimento.pdf", "CNIS.pdf", "Documento_Identidade.pdf"]
    )

@app.post("/auditar-processo", response_model=AuditoriaResponse)
async def auditar_processo(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas PDF")

    conteudo = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(conteudo)
        caminho = tmp.name

    try:
        texto = extrair_texto_pdf(caminho)
        if not texto:
            texto = extrair_texto_pdf_ocr(caminho)
        if not texto:
            return AuditoriaResponse(success=False, error="Não foi possível extrair texto do PDF.")

        dados_ia = extrair_dados_auditoria_ia(texto)
        if "erro" in dados_ia:
            return AuditoriaResponse(success=False, error=dados_ia["erro"])

        resultado = roteador_auditoria(dados_ia)
        return resultado
    except Exception as e:
        return AuditoriaResponse(success=False, error=str(e))
    finally:
        if os.path.exists(caminho):
            os.unlink(caminho)

@app.post("/analisar-processo-completo", response_model=ProcessoCompletoResponse)
async def analisar_processo_completo(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Envie pelo menos um PDF")

    textos_documentos = []

    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            continue
        conteudo = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(conteudo)
            caminho_temporario = tmp.name
        try:
            texto = extrair_texto_pdf(caminho_temporario)
            if not texto:
                texto = extrair_texto_pdf_ocr(caminho_temporario)
            if texto:
                textos_documentos.append({
                    "filename": file.filename,
                    "texto": texto
                })
        except Exception as e:
            print(f"Erro ao processar {file.filename}: {e}")
        finally:
            if os.path.exists(caminho_temporario):
                os.unlink(caminho_temporario)

    if not textos_documentos:
        return ProcessoCompletoResponse(success=False, error="Nenhum texto extraído dos PDFs")

    dados_pessoais = None
    vinculos = []

    for doc in textos_documentos:
        if "cnis" in doc["filename"].lower() or "NIT:" in doc["texto"]:
            dados_pessoais = extrair_dados_pessoais(doc["texto"])
            vinculos = parsear_vinculos_cnis(doc["texto"])
            break

    if supabase and dados_pessoais and dados_pessoais.nit:
        try:
            response_seg = supabase.table("segurados").upsert(
                {
                    "nome": dados_pessoais.nome,
                    "nit": dados_pessoais.nit,
                    "cpf": dados_pessoais.cpf,
                    "data_nascimento": dados_pessoais.data_nascimento,
                    "nome_mae": dados_pessoais.nome_mae,
                },
                on_conflict="nit"
            ).execute()
            if response_seg.data:
                segurado_id = response_seg.data[0]["id"]
            supabase.table("vinculos").delete().eq("nit", dados_pessoais.nit).execute()
            for v in vinculos:
                supabase.table("vinculos").insert({
                    "filename": "processo_completo",
                    "sequencia": v.sequencia,
                    "nit": v.nit,
                    "codigo_empregador": v.codigo_empregador,
                    "empregador": v.empregador,
                    "data_inicio": v.data_inicio,
                    "data_fim": v.data_fim,
                    "tipo_filiado": v.tipo_filiado,
                    "ultima_remuneracao": v.ultima_remuneracao,
                    "indicador": v.indicador
                }).execute()
        except Exception as e:
            print(f"Erro ao salvar: {e}")

    calculo_result = None
    sexo_padrao = "M"
    if dados_pessoais and dados_pessoais.nit:
        try:
            if supabase:
                response_seg = supabase.table("segurados").select("*").eq("nit", dados_pessoais.nit).execute()
                if response_seg.data:
                    sexo_padrao = response_seg.data[0].get("sexo") or "M"
            lista_vinculos = vinculos or []
            idade = calcular_idade(dados_pessoais.data_nascimento) if dados_pessoais else None
            total_dias, anos, meses, dias = calcular_tempo(lista_vinculos)
            carencia = calcular_carencia(lista_vinculos)
            tempo_anos_total = anos + (meses / 12) + (dias / 365)
            simulacao = simular_aposentadorias(idade, tempo_anos_total, carencia, sexo_padrao)
            calculo_result = CalculoResponse(
                success=True,
                idade=idade,
                tempo_contribuicao_anos=anos,
                tempo_contribuicao_meses=meses,
                tempo_contribuicao_dias=dias,
                carencia_meses=carencia,
                simulacao=simulacao
            )
        except Exception as e:
            calculo_result = CalculoResponse(success=False, error=str(e))

    auditoria_result = None
    texto_completo = "\n\n".join([f"=== {doc['filename']} ===\n{doc['texto'][:1500]}" for doc in textos_documentos])
    texto_completo = texto_completo[:6000]
    if LLM_API_KEY and texto_completo:
        dados_ia = extrair_dados_auditoria_ia(texto_completo)
        if "erro" in dados_ia:
            auditoria_result = AuditoriaResponse(success=False, error=dados_ia["erro"])
        else:
            auditoria_result = roteador_auditoria(dados_ia)

    return ProcessoCompletoResponse(
        success=True,
        dados_pessoais=dados_pessoais,
        vinculos=vinculos,
        calculo=calculo_result,
        auditoria=auditoria_result,
        documentos_analisados=[doc["filename"] for doc in textos_documentos],
    )

@app.post("/extrair-dados-ia", response_model=ExtracaoIAResponse)
async def extrair_dados_ia(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas PDF")

    conteudo = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(conteudo)
        caminho = tmp.name

    try:
        texto = extrair_texto_pdf(caminho)
        if not texto:
            texto = extrair_texto_pdf_ocr(caminho)
        if not texto:
            return ExtracaoIAResponse(success=False, error="Não foi possível extrair texto do PDF.")

        dados = extrair_dados_com_ia(texto)
        return ExtracaoIAResponse(
            success=True,
            dados=dados,
            texto_bruto=texto[:2000]
        )
    except Exception as e:
        return ExtracaoIAResponse(success=False, error=str(e))
    finally:
        if os.path.exists(caminho):
            os.unlink(caminho)

@app.get("/")
async def root():
    return {"mensagem": "API Previdenciária Completa rodando. Acesse /docs para testar."}
