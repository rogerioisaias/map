#!/usr/bin/env python3
"""Baixa a apuração de Presidente (eleição 6257) e Senado (eleição 6259) do TSE, 1º turno 2026,
e gera um painel HTML autocontido.

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

import historico

RAIZ = "https://resultados.tse.jus.br/oficial/ele2026"
BASE = f"{RAIZ}/6257"
ELEICAO, CARGO = "006257", "0001"
SENADO_ELEICAO, SENADO_CARGO = "6259", "0005"

# Classificação ideológica usada no placar do Senado. Ajuste aqui se discordar de algum partido.
ESPECTRO = {
    "esquerda": ["PT", "PSOL", "PCDOB", "PC do B", "PV", "REDE", "PSB", "PDT", "PCB", "PSTU", "UP", "PCO"],
    "centro": ["MDB", "PSD", "PSDB", "CIDADANIA", "SOLIDARIEDADE", "AVANTE", "AGIR", "MOBILIZA", "PODE", "PMB"],
    "direita": ["PL", "PP", "UNIÃO", "REPUBLICANOS", "NOVO", "PRD", "PRTB", "DC", "MISSÃO", "DEMOCRATA"],
}
ESPECTRO_DE = {sg.upper(): lado for lado, sgs in ESPECTRO.items() for sg in sgs}
CACHE = Path(__file__).resolve().parent / ".cache"
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


def baixar(url, tentativas=5):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(2 ** (i + 1))  # o TSE devolve 429 quando recebe muitas requisições seguidas


def foto_b64(eleicao, uf, sq):
    """Fotos não mudam durante a apuração: baixa uma vez e guarda em tse/.cache."""
    local = CACHE / "fotos" / eleicao / uf / f"{sq}.jpeg"
    try:
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(baixar(f"{RAIZ}/{eleicao}/fotos/{uf}/{sq}.jpeg"))
        return "data:image/jpeg;base64," + base64.b64encode(local.read_bytes()).decode()
    except Exception:
        return ""


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


def geometria():
    """Projeta a malha do IBGE (tse/geo/ufs-br.geojson) em coordenadas de tela.

    Devolve, por UF, o caminho SVG em tamanho real, o centroide e a área projetada.
    O painel usa esses valores para encolher cada estado em torno do próprio centro
    até a área ficar proporcional ao eleitorado (cartograma não contíguo).
    """
    import math
    escala, cosl = 20, math.cos(math.radians(15))
    proj = lambda lon, lat: ((lon + 74.2) * cosl * escala, (5.6 - lat) * escala)
    geo = json.loads((AQUI / "geo" / "ufs-br.geojson").read_text(encoding="utf-8"))
    saida = {}
    for f in geo["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        partes, area, cx, cy = [], 0.0, 0.0, 0.0
        for poly in polys:
            for i, anel in enumerate(poly):
                pts = [proj(*c) for c in anel]
                partes.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
                if i:
                    continue
                for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                    cr = x1 * y2 - x2 * y1
                    area += cr / 2
                    cx += (x1 + x2) * cr
                    cy += (y1 + y2) * cr
        saida[f["properties"]["uf"]] = {
            "d": "".join(partes), "a": round(abs(area), 1),
            "cx": round(cx / (6 * area), 1), "cy": round(cy / (6 * area), 1),
        }
    return saida


SENADO_API = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json"


def senado_atual():
    """Senadores em exercício (dados abertos do Senado), com partido e fim do mandato.

    Guarda a última resposta em tse/.cache para seguir funcionando se a API falhar.
    """
    local = CACHE / "senado-atual.json"
    try:
        bruto = baixar(SENADO_API)
        json.loads(bruto)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(bruto)
    except Exception:
        if not local.exists():
            return None
        bruto = local.read_bytes()
    d = json.loads(bruto)["ListaParlamentarEmExercicio"]
    lista = []
    for p in d["Parlamentares"]["Parlamentar"]:
        i, m = p["IdentificacaoParlamentar"], p["Mandato"]
        sg = i.get("SiglaPartidoParlamentar") or "S/Partido"
        lista.append({
            "nome": i["NomeParlamentar"], "sg": sg, "uf": m["UfParlamentar"],
            "fim": int(m["SegundaLegislaturaDoMandato"]["DataFim"][:4]),
            "lado": ESPECTRO_DE.get(sg.upper(), "sem"),
            "titular": m.get("DescricaoParticipacao") == "Titular",
        })
    return {"versao": d["Metadados"]["Versao"], "lista": sorted(lista, key=lambda x: (x["uf"], x["nome"]))}


def soma_ufs(brutos):
    """Total do Brasil somando as 27 UFs e o exterior.

    Usado quando o arquivo nacional do TSE está mais atrasado que os arquivos estaduais.
    """
    rs = [resumo(brutos[uf]) for uf in UFS]
    t = {k: sum(r[k] for r in rs) for k in ("st", "ts", "te", "c", "a", "tv", "vv", "vb", "vn")}
    votos = {}
    for uf in UFS:
        for c in candidatos(brutos[uf]):
            votos[c["n"]] = votos.get(c["n"], 0) + c["vap"]
    ultimo = max(rs, key=lambda r: (r["dg"][6:] + r["dg"][3:5] + r["dg"][:2], r["hg"]))
    pct = lambda a, b: a / b * 100 if b else 0.0
    return {
        "dg": ultimo["dg"], "hg": ultimo["hg"], "andamento": "p", "final": all(r["final"] for r in rs),
        "pst": pct(t["st"], t["ts"]), **t,
        "pc": pct(t["c"], t["c"] + t["a"]), "pa": pct(t["a"], t["c"] + t["a"]),
        "pvv": pct(t["vv"], t["tv"]), "pvb": pct(t["vb"], t["tv"]), "pvn": pct(t["vn"], t["tv"]),
    }, votos


def arquivo(uf):
    return f"{BASE}/dados/{uf}/{uf}-c{CARGO}-e{ELEICAO}-u.json"


def arquivo_senado(uf):
    return f"{RAIZ}/{SENADO_ELEICAO}/dados/{uf}/{uf}-c{SENADO_CARGO}-e00{SENADO_ELEICAO}-u.json"


def senado(uf, nome, d):
    vagas = int(d["carg"][0].get("nv") or 1)
    cands = candidatos(d)
    for i, c in enumerate(cands):
        c["lado"] = ESPECTRO_DE.get(c["sg"].upper(), "centro")
        c["foto"] = foto_b64(SENADO_ELEICAO, uf, c["sq"]) if i < vagas + 1 else ""
        for k in ("nm", "sq", "coligacao", "situacao"):
            c.pop(k, None)
    return {"uf": uf.upper(), "nome": nome, "vagas": vagas, **resumo(d), "cands": cands}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--saida")
    args = ap.parse_args()

    with ThreadPoolExecutor(4) as ex:
        brutos = dict(zip(["br", *UFS], ex.map(lambda u: json.loads(baixar(arquivo(u))), ["br", *UFS])))
        ufs_sen = [u for u in UFS if u != "zz"]
        sen_brutos = dict(zip(ufs_sen, ex.map(lambda u: json.loads(baixar(arquivo_senado(u))), ufs_sen)))

    nac = brutos["br"]
    oficial = {**resumo(nac), "p": {c["n"]: round(c["p"], 4) for c in candidatos(nac) if c["n"] in historico.FOCO}}
    cands = candidatos(nac)
    for c in cands:
        c["foto"] = foto_b64("6257", "br", c["sq"])

    brasil = {**resumo(nac), "fonte": "tse"}
    somado, votos = soma_ufs(brutos)
    if somado["st"] > brasil["st"]:
        # O arquivo nacional ficou para trás: usa a soma das UFs e guarda o dado oficial para comparação.
        brasil = {**somado, "fonte": "soma", "oficial": {"dg": brasil["dg"], "hg": brasil["hg"], "pst": brasil["pst"]}}
        for c in cands:
            c["vap"] = votos.get(c["n"], 0)
            c["p"] = c["vap"] / somado["vv"] * 100 if somado["vv"] else 0.0
        cands.sort(key=lambda c: -c["vap"])

    agora = datetime.now(BRT)
    dados = {
        "gerado": agora.strftime("%Y-%m-%d %Hh%M"),
        "fonte": "https://resultados.tse.jus.br/oficial/app/index.html#/eleicao/6257/uf/br/cargo/1/vis/nominal/resultados",
        "brasil": {**brasil, "cands": cands},
        "ufs": [
            {"uf": uf.upper(), "nome": nome, **resumo(brutos[uf]),
             "votos": {c["n"]: [c["vap"], c["p"]] for c in candidatos(brutos[uf])}}
            for uf, nome in UFS.items()
        ],
        "espectro": ESPECTRO,
        "geo": geometria(),
        "senadoAtual": senado_atual(),
        "senado": [senado(uf, UFS[uf], d) for uf, d in sen_brutos.items()],
    }

    hist = historico.acrescentar(historico.carregar(), historico.ponto(dados["ufs"], oficial))
    historico.salvar(hist)
    dados["historico"] = hist

    html = (AQUI / "template.html").read_text(encoding="utf-8")
    html = html.replace("__DATA__", json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__AUTORIA__", agora.strftime("%Y-%m-%d %Hh%M"))
    destino = Path(args.saida) if args.saida else AQUI / "saida" / f"apuracao-presidente-2026_{agora.strftime('%Y-%m-%d_%Hh%M')}.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    b = dados["brasil"]
    print(f"{destino}  |  Brasil: {b['pst']:.2f}% das seções totalizadas às {b['hg']}"
          f"{' (soma das UFs; arquivo nacional às ' + nac['hg'] + ')' if b['fonte'] == 'soma' else ''}"
          f"  |  Senado: última UF atualizada às {max(u['hg'] for u in dados['senado'])}")


if __name__ == "__main__":
    main()
