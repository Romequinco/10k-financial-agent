"""Exploracion local; no cambia el retrieval de produccion ni llama a una API.

Consultas manuales fijadas antes de medir esta rejilla. Se conoce el golden:
los resultados son exploratorios y no una validacion independiente.
Los filtros son oraculo, incluso cuando solo fijan ticker y ejercicio.
No se incluyen terminos extraidos de las respuestas/anclas en las consultas.
Ejecutar: python -B resultados/experimentos/ingles_20260917/experimento.py
"""
import os
import sys
import json
import time
import hashlib
from pathlib import Path
from importlib.metadata import version

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
sys.stdout.reconfigure(encoding='utf-8')
DESTINO = Path(__file__).resolve().parent
RAIZ = next(p for p in DESTINO.parents if (p / 'pyproject.toml').exists())
sys.path.insert(0, str(RAIZ / 'src'))
import pandas as pd
from agente10k import config, retrieval as r, evaluacion as e

def guardar(nombre, valor):
    (DESTINO / nombre).write_text(json.dumps(valor, ensure_ascii=False, indent=2), encoding='utf-8')

def fusion(listas, c=60, pesos=None):
    scores = {}
    for lista, peso in zip(listas, pesos or [1] * len(listas)):
        for rango, cid in enumerate(dict.fromkeys(lista), 1):
            scores[cid] = scores.get(cid, 0) + peso / (c + rango)
    return sorted(scores, key=scores.get, reverse=True)

def main():
    golden = e.cargar_golden(config.GOLDEN / 'golden_propio.jsonl')
    preguntas = [p for p in golden if p.get('ancla_texto')]
    consultas = json.loads((DESTINO / 'consultas.json').read_text(encoding='utf-8'))
    assert set(consultas) == {p['id'] for p in preguntas}
    fuentes = [Path(__file__), DESTINO / 'consultas.json', Path(r.__file__), Path(e.__file__),
               config.GOLDEN / 'golden_propio.jsonl', config.INDICE / 'corpus.faiss',
               config.INDICE / 'chunks_meta.parquet']
    protocolo = {
        'golden': golden, 'consultas': consultas, 'k': 5, 'n_candidatos': 20, 'rrf': 60,
        'filtros': ['ninguno', 'ticker_fy_oraculo', 'ticker_fy_item_oraculo'],
        'formas': ['literal', 'breve', 'expandida', 'multiquery'],
        'motores': ['denso', 'bm25', 'hibrido'],
        'notas': ['consultas manuales, no LLM desplegado', 'mismo golden conocido; no holdout',
                  'FY mas reciente en comparativas; no mide evidencia de ambos ejercicios',
                  'latencias cacheadas de esta rejilla no son comparables; se miden aparte'],
        'sha256': {str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest() for p in fuentes},
        'versiones': {n: version(n) for n in ('sentence-transformers', 'rank-bm25', 'faiss-cpu')},
    }
    guardar('protocolo.json', protocolo)
    print('Protocolo y consultas fijados; cargando recursos locales.', flush=True)
    r._cargar_recursos()
    textos = e.textos_retrieval()
    meta = r._leer_metadatos_cache().set_index('chunk_id')
    relevantes = {p['id']: e._relevantes(p, textos) for p in preguntas}
    scoped = {p['id']: {cid for cid in relevantes[p['id']]
                       if meta.loc[cid, 'ticker'] == p['ticker']
                       and int(meta.loc[cid, 'fiscal_year']) == p['fiscal_year']
                       and meta.loc[cid, 'item'] == p['item_esperado']} for p in preguntas}
    dense, lexical = {}, {}
    for q in dict.fromkeys(q for qs in consultas.values() for q in qs):
        dense[q] = [d['chunk_id'] for d in r.buscar_denso(q, k=len(meta))]
        lexical[q] = [d['chunk_id'] for d in r.buscar_bm25(q, k=len(meta))]
    guardar('rankings_senales.json', {'denso': dense, 'bm25': lexical})
    print('Senales calculadas:', len(dense), 'consultas unicas.', flush=True)
    resumen, detalle, rankings = [], [], {}

    def registrar(nombre, por_pregunta, **etiquetas):
        rankings[nombre] = por_pregunta
        summary = {'variante': nombre, **etiquetas, 'n': len(preguntas)}
        rangos = []
        for p in preguntas:
            ids = por_pregunta[p['id']]
            assert len(ids) == len(set(ids)) and all(cid in textos for cid in ids)
            rango = next((i for i, cid in enumerate(ids, 1) if cid in relevantes[p['id']]), None)
            rango_ctx = next((i for i, cid in enumerate(ids, 1) if cid in scoped[p['id']]), None)
            rangos.append((rango, rango_ctx))
            detalle.append({'variante': nombre, 'id': p['id'], 'familia': p['familia'],
                            'rango': rango, 'rango_contexto': rango_ctx,
                            'hit5': rango is not None and rango <= 5,
                            'hit5_contexto': rango_ctx is not None and rango_ctx <= 5})
        for k in (1, 3, 5, 10, 20):
            h = sum(a is not None and a <= k for a, b in rangos)
            summary[f'hits@{k}'] = h
            summary[f'recall@{k}'] = h / len(preguntas)
        summary['hits@5_contexto'] = sum(b is not None and b <= 5 for a, b in rangos)
        summary['mrr@10'] = sum(1 / a for a, b in rangos if a is not None and a <= 10) / len(preguntas)
        resumen.append(summary)

    for scope in protocolo['filtros']:
        for forma in protocolo['formas']:
            for motor in protocolo['motores']:
                nombre = f'{scope}__{forma}__{motor}'
                filas = {}
                for p in preguntas:
                    kw = {} if scope == 'ninguno' else {'ticker': p['ticker'], 'fiscal_year': p['fiscal_year']}
                    if scope == 'ticker_fy_item_oraculo': kw['item'] = p['item_esperado']
                    permitidos = set(meta.index[r.candidatos(**kw)])
                    qs = consultas[p['id']]
                    qs = {'literal': qs[:1], 'breve': qs[1:2], 'expandida': qs[2:3], 'multiquery': qs}[forma]
                    listas = []
                    for q in qs:
                        if motor in ('denso', 'hibrido'): listas.append([c for c in dense[q] if c in permitidos][:20])
                        if motor in ('bm25', 'hibrido'): listas.append([c for c in lexical[q] if c in permitidos][:20])
                    filas[p['id']] = fusion(listas)[:20]
                registrar(nombre, filas, filtro=scope, consulta=forma, motor=motor)
    guardar('rankings.json', rankings)
    pd.DataFrame(resumen).to_csv(DESTINO / 'resumen.csv', index=False)
    pd.DataFrame(detalle).to_csv(DESTINO / 'detalle.csv', index=False)
    print(pd.DataFrame(resumen).sort_values(['hits@5', 'mrr@10'], ascending=False)
          [['variante','hits@5','hits@5_contexto','hits@10','mrr@10']].to_string(index=False), flush=True)

if __name__ == '__main__': main()
