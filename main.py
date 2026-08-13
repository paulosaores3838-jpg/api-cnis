from fastapi import FastAPI, UploadFile, File, HTTPException
import pdfplumber
import re
import tempfile
import os
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="API CNIS", version="0.1.0")

# Modelo de resposta
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

class CnisResponse(BaseModel):
    filename: str
    success: bool
    vinculos: List[Vinculo] = []
    error: Optional[str] = None

def extrair_texto_pdf(caminho_arquivo):
    texto = ""
    with pdfplumber.open(caminho_arquivo) as pdf:
        for pagina in pdf.pages:
            conteudo = pagina.extract_text()
            if conteudo:
                texto += conteudo + "\n"
    return texto.strip()

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
            # Linha anterior pode conter "Empregado ou"
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

                # Encontra datas
                padrao_data = re.compile(r'\d{2}/\d{2}/\d{4}')
                datas = padrao_data.findall(linha)
                if len(datas) >= 2:
                    data_inicio = datas[0]
                    data_fim = datas[1]
                else:
                    data_inicio = data_fim = ""

                # Empregador: entre código e data início
                match_emp = re.search(rf'{codigo_empregador}\s+(.*?)\s+{data_inicio}', linha)
                empregador = match_emp.group(1).strip() if match_emp else "Não identificado"

                # Resto após data fim
                resto = linha.split(data_fim)[-1].strip() if data_fim else ""
                match_resto = re.search(r'(\d{2}/\d{4})\s+(\S+)', resto)
                ultima_remuneracao = match_resto.group(1) if match_resto else ""
                indicador = match_resto.group(2) if match_resto else resto

                # Linha seguinte pode conter "Agente Pblico"
                if i+1 < len(linhas):
                    proxima = linhas[i+1].strip()
                    if "Agente" in proxima:
                        tipo_filiado += proxima
                        i += 1  # Pula a linha

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
        vinculos = parsear_vinculos_cnis(texto)
        return CnisResponse(
            filename=file.filename,
            success=True,
            vinculos=vinculos
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
