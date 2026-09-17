"""Segunda fase exploratoria: equivalencia, sensibilidad y tiempos locales.

Se ejecuta despues de experimento.py. Las variantes de esta fase se proponen
tras ver la primera rejilla: no son un test independiente ni un holdout.
"""
import json
import time
import re
import statistics
from pathlib import Path
from experimento import DESTINO, guardar, fusion, config, r, e, pd

PARAFRASIS = [
    'third party abuse of AI systems and associated risks',
    'risks of relying on few manufacturing suppliers',
    'exposure to changes in foreign currency exchange rates',
    'AWS operating performance and business growth',
    'regulatory risks relating to antitrust and competition',
    'contractual commitments and lease obligations',
    'reasons for changes in total revenue',
    'reasons for changes in total revenue',
    'reasons for changes in total revenue',
    'reasons for changes in research and development spending',
    'reasons for changes in cash and cash equivalents',
    'reasons for changes in cash flow from operations',
    'comparability of basic earnings per share across fiscal years',
]

STOP = set('according to its what does say about of by in from a an the how did and is that between two with or for on at as it this these those fiscal year years fy2024 fy2025 2024 2025 report describe indicate explain management regards regarding states statements financial total'.split())
EMPRESAS = set('microsoft msft nvidia nvda apple aapl amazon amzn alphabet google googl meta'.split())

def limpiar(q):
    return ' '.join(t for t in re.findall('[a-z0-9]+', q.lower()) if t not in STOP | EMPRESAS and t != '10')

def main():
    ps = [p for p in e.cargar_golden(config.GOLDEN/'golden_propio.jsonl') if p.get('ancla_texto')]
    qs = json.loads((DESTINO/'consultas.json').read_text(encoding='utf-8'))
    ranks = json.loads((DESTINO/'rankings.json').read_text(encoding='utf-8'))
    senales = json.loads((DESTINO/'rankings_senales.json').read_text(encoding='utf-8'))
    tx = e.textos_retrieval()
    meta = r._leer_metadatos_cache().set_index('chunk_id')
    rel = {p['id']: e._relevantes(p, tx) for p in ps}
    consultas_nuevas = {p['id']: {'parafrasis': q, 'limpieza_generica': limpiar(qs[p['id']][0])}
                       for p,q in zip(ps,PARAFRASIS)}
    guardar('consultas_segunda_fase.json', consultas_nuevas)
    r._cargar_recursos()
    verificadas = 0
    for p in ps:
        kw = e.filtros_oraculo(p)
        for modo,func,ind in [('expandida__denso',r.buscar_denso,2),('breve__bm25',r.buscar_bm25,1)]:
            directo = [d['chunk_id'] for d in func(qs[p['id']][ind], k=20, **kw)]
            assert directo == ranks['ticker_fy_item_oraculo__'+modo][p['id']]
            verificadas += 1
    print('Rankings verificados contra funciones originales:', verificadas, flush=True)
    resultados, detalle, nuevos_rankings = [], [], {}

    def registrar(nombre, filas):
        nuevos_rankings[nombre] = filas
        rangos,ctx = [],[]
        for p in ps:
            rr=next((i for i,c in enumerate(filas[p['id']],1) if c in rel[p['id']]),None)
            rc=next((i for i,c in enumerate(filas[p['id']],1) if c in rel[p['id']]
                     and meta.loc[c,'ticker']==p['ticker'] and int(meta.loc[c,'fiscal_year'])==p['fiscal_year']
                     and meta.loc[c,'item']==p['item_esperado']),None)
            rangos.append(rr);ctx.append(rc)
            detalle.append({'variante':nombre,'id':p['id'],'rango':rr,'rango_contexto':rc})
        resultados.append({'variante':nombre,'hits@5':sum(x is not None and x<=5 for x in rangos),
                           'hits@5_contexto':sum(x is not None and x<=5 for x in ctx),
                           'hits@10':sum(x is not None and x<=10 for x in rangos)})

    for scope in ['ticker_fy_oraculo','ticker_fy_item_oraculo']:
        for forma in ['parafrasis','limpieza_generica']:
            for motor,func in [('denso',r.buscar_denso),('bm25',r.buscar_bm25)]:
                filas={}
                for p in ps:
                    kw=e.filtros_oraculo(p)
                    if scope=='ticker_fy_oraculo':kw.pop('item')
                    filas[p['id']]=[d['chunk_id'] for d in func(consultas_nuevas[p['id']][forma],k=20,**kw)]
                registrar(f'{scope}__{forma}__{motor}',filas)
        # Una consulta por senal; mismos candidatos y RRF que la rejilla.
        filas={}
        for p in ps:
            kw=e.filtros_oraculo(p)
            if scope=='ticker_fy_oraculo':kw.pop('item')
            permitidos=set(meta.index[r.candidatos(**kw)])
            dd=[cid for cid in senales['denso'][qs[p['id']][2]] if cid in permitidos][:20]
            bb=[cid for cid in senales['bm25'][qs[p['id']][1]] if cid in permitidos][:20]
            filas[p['id']]=fusion([dd,bb])[:20]
        registrar(f'{scope}__expandida_denso_breve_bm25',filas)

    # Cronometra el backend local, no la traduccion manual ni el agente final.
    latencias=[]
    for motor,func,ind in [('denso_expandida',r.buscar_denso,2),('bm25_breve',r.buscar_bm25,1)]:
        tiempos=[]
        for vuelta in range(3):
            for p in ps:
                t=time.perf_counter()
                func(qs[p['id']][ind],k=5,**e.filtros_oraculo(p))
                tiempos.append(1000*(time.perf_counter()-t))
        latencias.append({'motor':motor,'n':len(tiempos),'media_ms':statistics.mean(tiempos),
                          'mediana_ms':statistics.median(tiempos),'min_ms':min(tiempos),'max_ms':max(tiempos)})
    guardar('verificacion.json',{'rankings_iguales':verificadas,'latencias_backend_caliente':latencias})
    guardar('rankings_segunda_fase.json',nuevos_rankings)
    pd.DataFrame(resultados).to_csv(DESTINO/'resumen_segunda_fase.csv',index=False)
    pd.DataFrame(detalle).to_csv(DESTINO/'detalle_segunda_fase.csv',index=False)
    print(pd.DataFrame(resultados).to_string(index=False),flush=True)
    print(json.dumps(latencias,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
