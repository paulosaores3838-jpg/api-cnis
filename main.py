from fastapi import FastAPI, UploadFile, File, HTTPException, Query
import pdfplumber
import re
import tempfile
import os
from pydantic import BaseModel
from typing import Optional, List
from supabase import create_client, Client
from datetime import datetime, date

app = FastAPI(title="API CNIS", version="0.3.0")

# Configuração Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

class CnisResponse(BaseModel):
    filename: str
    success: bool
    dados_pessoais: Optional[DadosPessoais] = None
    vinculos: List[Vinculo] = []
    error: Optional[str] = None
    saved: bool = False
    segurado_id: Optional[str] = None

class CalculoResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    idade: Optional[str] = None
    tempo_contribuicao_anos: Optional[int] = None
    tempo_contribuicao_meses: Optional[int] = None
    tempo_contribuicao_dias: Optional[int] = None
    carencia_meses: Optional[int] = None
    simulação: Optional[dict] = None

# ========== FUNÇÕES AUXILIARES ==========
def extrair_texto_pdf(caminho_arquivo):
    texto = ""
    with pdfplumber.open(caminho_arquivo) as pdf:
        for pagina in pdf.pages:
            conteudo = pagina.extract_text()
            if conteudo:
                texto += conteudo + "\n"
    return texto.strip()

def extrair_dados_pessoais(texto):
    dados = DadosPessoais()
    # NIT
    m = re.search(r'NIT:\s*(\d{3}\.\d{5}\.\d{2}-\d)', texto)
    if m:
        dados.nit = m.group(1)
    # CPF
    m = re.search(r'CPF:\s*(\d{3}\.\d{3}\.\d{3}-\d{2})', texto)
    if m:
        dados.cpf = m.group(1)
    # Nome
    m = re.search(r'Nome:\s*(.*)', texto)
    if m:
        dados.nome = m.group(1).strip()
    # Data de nascimento
    m = re.search(r'Data de nascimento:\s*(\d{2}/\d{2}/\d{4})', texto)
    if m:
        dados.data_nascimento = m.group(1)
    # Nome da mãe
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

def calcular_tempo(vinculos):
    """Calcula tempo total em dias a partir dos vínculos."""
    total_dias = 0
    for v in vinculos:
        if v.data_inicio and v.data_fim:
            try:
                di = datetime.strptime(v.data_inicio, "%d/%m/%Y")
                df = datetime.strptime(v.data_fim, "%d/%m/%Y")
                if df < di:
                    continue
                dias = (df - di).days + 1
                total_dias += dias
            except:
                pass
    anos = total_dias // 365
    meses = (total_dias % 365) // 30
    dias_rest = (total_dias % 365) % 30
    return total_dias, anos, meses, dias_rest

def calcular_carencia(vinculos):
    """Conta meses de contribuição distintos."""
    meses_set = set()
    for v in vinculos:
        if v.data_inicio and v.data_fim:
            try:
                di = datetime.strptime(v.data_inicio, "%d/%m/%Y")
                df = datetime.strptime(v.data_fim, "%d/%m/%Y")
                # percorre meses entre di e df
                while di <= df:
                    meses_set.add((di.year, di.month))
                    # avança para próximo mês
                    if di.month == 12:
                        di = di.replace(year=di.year+1, month=1, day=1)
                    else:
                        di = di.replace(month=di.month+1, day=1)
            except:
                pass
    return len(meses_set)

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
            return CnisResponse(
                filename=file.filename,
                success=False,
                error="Não foi possível extrair texto. PDF pode ser escaneado."
            )

        # Extrai dados pessoais
        dados_pessoais = extrair_dados_pessoais(texto)
        vinculos = parsear_vinculos_cnis(texto)

        saved = False
        segurado_id = None

        if supabase:
            try:
                # Salva dados pessoais na tabela segurados
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
                    # Salva vínculos vinculados ao segurado
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
                saved = True
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

@app.get("/")
async def root():
    return {"mensagem": "API CNIS rodando. Acesse /docs para testar."}
