"""Confirma la alternativa simple extrayendo filtros del texto de la pregunta.

Traduccion al ingles aun manual. Empresa y FY se extraen por alias y regex;
en comparativas se busca aqui solo el FY mas reciente. No resuelve la obtencion
de ambos ejercicios ni la respuesta completa. No usa anclas para recuperar.
"""
import re
import json
from comprobaciones import limpiar
from experimento import DESTINO, guardar, r, e, config

ALIASES = {
    'MSFT': ['MSFT', 'Microsoft'], 'NVDA': ['NVDA', 'NVIDIA'],
    'AAPL': ['AAPL', 'Apple'], 'AMZN': ['AMZN', 'Amazon'],
    'GOOGL': ['GOOGL', 'GOOG', 'Alphabet', 'Google'], 'META': ['META', 'Facebook'],
}

def extraer(texto):
    empresas = [t for t, aliases in ALIASES.items()
                if any(re.search(r'\b'+re.escape(a)+r'\b', texto, re.IGNORECASE) for a in aliases)]
    fys = [int(v) for v in re.findall(r'(?:FY\s*)?\b(20\d{2})\b', texto, re.IGNORECASE)]
    # En FY2025 no hay limite de palabra entre Y y 2: aceptar tambien ese caso.
    fys += [int(v) for v in re.findall(r'FY\s*(20\d{2})\b', texto, re.IGNORECASE)]
    return {'ticker': empresas[0] if len(empresas)==1 else None,
            'fiscal_year': max(fys) if fys else None}

def main():
    preguntas = [p for p in e.cargar_golden(config.GOLDEN/'golden_propio.jsonl') if p.get('ancla_texto')]
    qs = json.loads((DESTINO/'consultas.json').read_text(encoding='utf-8'))
    previos = json.loads((DESTINO/'rankings_segunda_fase.json').read_text(encoding='utf-8'))
    textos = e.textos_retrieval()
    filas=[]
    for p in preguntas:
        filtros=extraer(p['pregunta'])
        consulta=limpiar(qs[p['id']][0])
        docs=r.buscar_denso(consulta,k=20,**filtros)
        ranking=[d['chunk_id'] for d in docs]
        assert ranking==previos['ticker_fy_oraculo__limpieza_generica__denso'][p['id']]
        # El golden interviene solo despues de recuperar, para puntuar y auditar filtros.
        rel=e._relevantes(p,textos)
        rango=next((i for i,c in enumerate(ranking,1) if c in rel),None)
        filas.append({'id':p['id'],'query':consulta,'filtros':filtros,'ranking':ranking,'rango':rango,
                      'filtros_correctos':filtros=={'ticker':p['ticker'],'fiscal_year':p['fiscal_year']}})
    resultado={'n':len(filas),'hits@5':sum(f['rango'] is not None and f['rango']<=5 for f in filas),
               'filtros_correctos':sum(f['filtros_correctos'] for f in filas),'filas':filas,
               'limite':'traducciones manuales; corpus cerrado; FY mas reciente; evaluacion exploratoria'}
    guardar('filtros_desde_pregunta.json',resultado)
    print({k:v for k,v in resultado.items() if k!='filas'},flush=True)

if __name__=='__main__':main()
