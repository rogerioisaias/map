#!/usr/bin/env python3
"""Baixa a apuração de Presidente (TSE, eleição 6257, 1º turno 2026) e gera um painel HTML autocontido.

Uso:
    python3 tse/gerar_painel.py            # gera tse/saida/apuracao-presidente-2026_<data>_<hora>.html
    python3 tse/gerar_painel.py -o x.html  # grava em um caminho fixo
"""
import argparse
import base64
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://resultados.tse.jus.br/oficial/ele2026/6257"
ELEICAO, CARGO = "006257", "0001"
UFS = {
    "ac": "Acre", "al": "Alagoas", "am": "Amazonas", "ap": "Amapá", "ba": "Bahia", "ce": "Ceará",
    "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás", "ma": "Maranhão",
    "mg": "Minas Gerais", "ms": "Mato Grosso do Sul", "mt": "Mato Grosso", "pa": "Pará",
    "pb": "Paraíba", "pe": "Pernambuco", "pi": "Piauí", "pr": "Paraná", "rj": "Rio de Janeiro",
    "rn": "Rio Grande do Norte", "ro": "Rondônia", "rr": "Roraima", "rs": "Rio Grande do Sul",
    "sc": "Santa Catarina", "se": "Sergipe", "sp": "São Paulo", "to": "Tocantins", "zz": "Exterior",
}
BRT = timezone(timedelta(hours=-3))
AQUI = Path(__file__).resolve().parent


def baixar(url, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(2 ** (i + 1))


def num(x):
    return float(str(x).replace(",", ".")) if x not in (None, "") else 0.0


def resumo(d):
    s, e, v = d["s"], d["e"], d["v"]
    return {
        "dg": d["dg"], "hg": d["hg"], "andamento": d.get("and"), "final": d.get("tf") == "s",
        "pst": num(s["pstn"]), "st": int(s["st"]), "ts": int(s["ts"]),
        "te": int(e["te"]), "c": int(e["c"]), "pc": num(e["pcn"]), "a": int(e["a"]), "pa": num(e["pan"]),
        "tv": int(v["tv"]), "vv": int(v["vv"]), "pvv": num(v["pvvcn"]),
        "vb": int(v["vb"]), "pvb": num(v["pvbn"]), "vn": int(v["tvn"]), "pvn": num(v["ptvnn"]),
    }


def candidatos(d):
    out = []
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                vice = c["vs"][0] if c.get("vs") else {}
                out.append({
                    "n": c["n"], "sq": c["sqcand"], "nmu": c["nmu"], "nm": c["nm"], "sg": par["sg"],
                    "com": agr["com"], "coligacao": agr["nm"] if agr["tp"] == "c" else "",
                    "vice": vice.get("nmu", ""), "vicesg": vice.get("sgp", ""),
                    "vap": int(c["vap"] or 0), "p": num(c["pvapn"]), "eleito": c["e"] == "s",
                    "situacao": c.get("st", ""), "destino": c.get("dvt", ""),
                })
    return sorted(out, key=lambda c: -c["vap"])


def arquivo(uf):
    return f"{BASE}/dados/{uf}/{uf}-c{CARGO}-e{ELEICAO}-u.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--saida")
    args = ap.parse_args()

    with ThreadPoolExecutor(8) as ex:
        brutos = dict(zip(["br", *UFS], ex.map(lambda u: json.loads(baixar(arquivo(u))), ["br", *UFS])))

    nac = brutos["br"]
    cands = candidatos(nac)

    def foto(c):
        try:
            return "data:image/jpeg;base64," + base64.b64encode(baixar(f"{BASE}/fotos/br/{c['sq']}.jpeg")).decode()
        except Exception:
            return ""

    with ThreadPoolExecutor(6) as ex:
        for c, f in zip(cands, ex.map(foto, cands)):
            c["foto"] = f

    agora = datetime.now(BRT)
    dados = {
        "gerado": agora.strftime("%Y-%m-%d %Hh%M"),
        "fonte": "https://resultados.tse.jus.br/oficial/app/index.html#/eleicao/6257/uf/br/cargo/1/vis/nominal/resultados",
        "brasil": {**resumo(nac), "cands": cands},
        "ufs": [
            {"uf": uf.upper(), "nome": nome, **resumo(brutos[uf]),
             "votos": {c["n"]: [c["vap"], c["p"]] for c in candidatos(brutos[uf])}}
            for uf, nome in UFS.items()
        ],
    }

    html = (AQUI / "template.html").read_text(encoding="utf-8")
    html = html.replace("__DATA__", json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__AUTORIA__", agora.strftime("%Y-%m-%d %Hh%M"))
    destino = Path(args.saida) if args.saida else AQUI / "saida" / f"apuracao-presidente-2026_{agora.strftime('%Y-%m-%d_%Hh%M')}.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    print(f"{destino}  |  Brasil: {dados['brasil']['pst']:.2f}% das seções totalizadas às {nac['hg']}")


if __name__ == "__main__":
    main()
