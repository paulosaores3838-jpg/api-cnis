from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import pdfplumber
import re
import tempfile
import os
import base64
from datetime import datetime, date
from supabase import create_client, Client
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import requests
import json

# ========== CONFIGURAÇÃO ==========
app = FastAPI(title="API Previdenciária Completa", version="1.0.0")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurações de IA (opcional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Caminho do Tesseract (opcional, se não estiver no PATH)
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
    tipo_documento: Optional[str] = None  # ex: "PPP", "LAUDO", "CARTERA"
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
    """Extrai texto de PDF escaneado usando OCR."""
    texto = ""
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    doc = fitz.open(caminho_arquivo)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=300)
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
    """Simplificação: identifica vínculos com indicador de tempo especial e calcula tempo especial total."""
    tempo_especial_dias = 0
    for v in vinculos:
        if v.indicador and ("ESPECIAL" in v.indicador.upper() or "INDPEND" in v.indicador.upper()):
            # Assumimos que todo o período do vínculo foi especial (simplificação)
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
    # Por idade
    idade_minima = 65 if sexo == "M" else 62
    sim["aposentadoria_idade"] = {
        "idade_atual": idade,
        "idade_necessaria": idade_minima,
        "carencia_atual": carencia_meses,
        "carencia_necessaria": 180,
        "elegivel": (idade >= idade_minima and carencia_meses >= 180)
    }
    # Por tempo
    tempo_necessario = 35 if sexo == "M" else 30
    sim["aposentadoria_tempo"] = {
        "tempo_atual_anos": round(tempo_anos_total, 2),
        "tempo_necessario": tempo_necessario,
        "elegivel": (tempo_anos_total >= tempo_necessario)
    }
    # Pontos (transição)
    pontos_necessarios = 101 if sexo == "M" else 91
    pontos_atuais = idade + tempo_anos_total
    sim["aposentadoria_pontos"] = {
        "pontos_atuais": round(pontos_atuais, 1),
        "pontos_necessarios": pontos_necessarios,
        "elegivel": (pontos_atuais >= pontos_necessarios)
    }
    # Pedágio 50% (simplificado)
    if sexo == "M":
        pedagio_necessario = 35
    else:
        pedagio_necessario = 30
    # Implementação simplificada
    sim["aposentadoria_pedagio_50"] = {
        "tempo_necessario": pedagio_necessario,
        "tempo_atual": round(tempo_anos_total, 2),
        "elegivel": (tempo_anos_total >= pedagio_necessario)  # precisa refinamento
    }
    return sim

# ========== ANÁLISE COM IA (OPCIONAL) ==========
def analisar_texto_com_ia(texto: str, tipo_documento: str) -> Dict[str, Any]:
    """Usa OpenAI para extrair dados estruturados de documentos previdenciários."""
    if not OPENAI_API_KEY:
        return {"erro": "Chave OpenAI não configurada"}
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = f"""
        Você é um assistente especializado em direito previdenciário brasileiro.
        Analise o seguinte documento ({tipo_documento}) e extraia os dados relevantes em formato JSON.
        Documento:
        {texto[:4000]}
        Retorne apenas JSON válido, sem texto adicional.
        """
        payload = {
            "model": OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            # Tenta parsear JSON
            try:
                return json.loads(content)
            except:
                return {"resumo": content}
        else:
            return {"erro": f"Falha na API: {response.status_code}"}
    except Exception as e:
        return {"erro": str(e)}

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
            texto = extrair_texto_pdf_ocr(caminho)  # fallback para OCR
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
        anos_especiais, meses_especiais, dias_especiais = calcular_tempo_especial(lista_vinculos)

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
    """Recebe texto bruto de um documento e usa IA para extrair dados."""
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
    """
    Endpoint de simulação de consulta processual no Meu INSS.
    Futuramente será integrado com automação real (RPA).
    """
    if not protocolo and not nit:
        return ProcessoConsultaResponse(success=False, error="Informe protocolo ou NIT")

    # Dados mockados para teste
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

@app.get("/")
async def root():
    return {"mensagem": "API Previdenciária Completa rodando. Acesse /docs para testar."}
