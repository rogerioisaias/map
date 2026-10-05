#!/usr/bin/env python3
"""Baixa o resultado de Presidente em cada município (arquivos do TSE, um por município).

Guarda um resumo em tse/.cache/municipios-presidente.json, indexado pelo código IBGE.
Município com apuração encerrada não é baixado de novo. Uso:
    python3 tse/municipios.py            # uma passada
    python3 tse/municipios.py --loop 180 # repete a cada 180 s, para rodar em segundo plano
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from gerar_painel import BASE, CACHE, baixar, candidatos

AQUI = Path(__file__).resolve().parent
SAIDA = CACHE / "municipios-presidente.json"


def lista():
    cfg = json.loads((AQUI / "geo" / "municipios-tse.json").read_text(encoding="utf-8"))
    return [(abr["cd"], m["cd"], m["cdi"], m["nm"]) for abr in cfg["abr"] if abr["cd"] != "zz" for m in abr["mu"]]


def resumo(uf, cd, nome):
    d = json.loads(baixar(f"{BASE}/dados/{uf}/{uf}{cd}-c0001-e006257-u.json", tentativas=6))
    cs = candidatos(d)
    s = d["s"]
    return {
        "nm": nome.title(), "uf": uf.upper(), "hg": d["hg"],
        "pst": round(float(s["pstn"].replace(",", ".")), 2),
        "fim": d.get("and") == "f" or d.get("tf") == "s",
        "c": [[c["n"], round(c["p"], 2), c["vap"]] for c in cs[:2]],
    }


def passada(atual):
    pend = [m for m in lista() if not atual.get(m[2], {}).get("fim")]
    ok = 0
    with ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(resumo, uf, cd, nm): cdi for uf, cd, cdi, nm in pend}
        for f, cdi in futs.items():
            try:
                atual[cdi] = f.result()
                ok += 1
            except Exception:
                pass
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    tmp = SAIDA.with_suffix(".tmp")
    tmp.write_text(json.dumps(atual, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(SAIDA)
    fim = sum(1 for v in atual.values() if v["fim"])
    print(time.strftime("%H:%M:%S"), f"baixados {ok}/{len(pend)} pendentes · {len(atual)} municípios · {fim} encerrados", flush=True)
    return atual


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0)
    a = ap.parse_args()
    try:
        atual = json.loads(SAIDA.read_text(encoding="utf-8"))
    except Exception:
        atual = {}
    while True:
        atual = passada(atual)
        if not a.loop or all(v["fim"] for v in atual.values()) and len(atual) >= len(lista()):
            break
        time.sleep(a.loop)
