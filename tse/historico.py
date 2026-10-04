"""Histórico da apuração: um ponto por atualização dos arquivos do TSE.

Cada ponto guarda o total somado das UFs (Presidente), o arquivo nacional oficial,
o horário e o percentual de cada UF. O painel usa isso para os gráficos de tendência,
as pausas entre atualizações e os surtos de apuração.
"""
import json
import re
import subprocess
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARQUIVO = AQUI / "saida" / "historico-apuracao.json"
PAINEL = "tse/saida/apuracao-presidente-2026_2026-10-04_18h26.html"
FOCO = ("22", "13")  # candidatos acompanhados nos gráficos


def iso(dg, hg):
    d, m, a = dg.split("/")
    return f"{a}-{m}-{d}T{hg}"


def ponto(ufs, oficial):
    """ufs: lista de dicts com uf, dg, hg, st, ts, vv e votos {n: [vap, p]}; oficial: dict com dg, hg, pst e votos opcionais."""
    st = sum(u["st"] for u in ufs)
    ts = sum(u["ts"] for u in ufs)
    vv = sum(u["vv"] for u in ufs)
    votos = {n: sum(u["votos"].get(n, [0])[0] for u in ufs) for n in FOCO}
    return {
        "t": max(iso(u["dg"], u["hg"]) for u in ufs),
        "pst": round(st / ts * 100, 4) if ts else 0, "st": st, "vv": vv,
        "votos": votos,
        "p": {n: round(v / vv * 100, 4) if vv else 0 for n, v in votos.items()},
        "oficial": {"t": iso(oficial["dg"], oficial["hg"]), "pst": round(oficial["pst"], 4),
                    "p": oficial.get("p")},
        "ufs": {u["uf"]: [iso(u["dg"], u["hg"]), round(u["pst"], 3)] for u in ufs},
    }


def carregar():
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except Exception:
        return []


def acrescentar(hist, novo):
    """Só guarda o ponto se a soma das UFs (horário ou seções) ou o arquivo oficial mudou."""
    if hist and hist[-1]["t"] == novo["t"] and hist[-1]["st"] == novo["st"] and hist[-1]["oficial"]["t"] == novo["oficial"]["t"]:
        return hist
    return [*hist, novo]


def salvar(hist):
    ARQUIVO.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def de_painel(html):
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html).group(1))
    b = d["brasil"]
    if b.get("fonte") == "soma":
        of = {**b["oficial"]}
    else:
        of = {"dg": b["dg"], "hg": b["hg"], "pst": b["pst"],
              "p": {c["n"]: round(c["p"], 4) for c in b["cands"] if c["n"] in FOCO}}
    return ponto(d["ufs"], of)


def reconstruir():
    """Refaz o histórico a partir das versões do painel salvas no Git."""
    shas = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", PAINEL],
                          cwd=AQUI.parent, capture_output=True, text=True, check=True).stdout.split()
    hist = []
    for sha in shas:
        html = subprocess.run(["git", "show", f"{sha}:{PAINEL}"], cwd=AQUI.parent,
                              capture_output=True, text=True, check=True).stdout
        try:
            p = de_painel(html)
        except Exception:
            continue
        hist = acrescentar(hist, p)
    hist.sort(key=lambda p: p["t"])
    return hist


if __name__ == "__main__":
    h = reconstruir()
    salvar(h)
    print(len(h), "pontos;", h[0]["t"], "a", h[-1]["t"])
