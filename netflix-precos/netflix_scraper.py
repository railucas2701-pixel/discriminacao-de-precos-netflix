"""
Scraper dos preços da Netflix em todos os países, a partir da Central de Ajuda:
    https://help.netflix.com/en/node/24926/<código do país>

Etapas:
  1. coletar   - baixa a página de cada um dos 249 códigos ISO de país (e um código inválido,
                 "xx", que serve de referência da página padrão). Salva o HTML em cache.
  2. processar - lê os planos e preços de cada página, converte para US$ com o câmbio do dia
                 (open.er-api.com), classifica nas regiões da Netflix e gera os CSVs.

Uso:
  pip install requests beautifulsoup4 pycountry babel country_converter
  python netflix_scraper.py            # coleta (pula páginas já baixadas) e processa
  python netflix_scraper.py coletar
  python netflix_scraper.py processar
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone

import requests

URL = "https://help.netflix.com/en/node/24926/{cc}"
URL_CAMBIO = "https://open.er-api.com/v6/latest/USD"
CODIGO_INVALIDO = "xx"  # devolve a página padrão (a do país do IP de quem acessa)
PAUSA_SEGUNDOS = 2.0
USER_AGENT = "Mozilla/5.0 (compatible; netflix-price-research)"


# ---------------------------------------------------------------- coleta

def codigos_paises():
    import pycountry
    return sorted(c.alpha_2.lower() for c in pycountry.countries)


def coletar(cache):
    os.makedirs(cache, exist_ok=True)
    sessao = requests.Session()
    sessao.headers["User-Agent"] = USER_AGENT
    codigos = [CODIGO_INVALIDO] + codigos_paises()
    baixadas = 0
    for i, cc in enumerate(codigos, 1):
        caminho = os.path.join(cache, f"{cc}.html")
        if os.path.exists(caminho):
            continue
        for tentativa in range(3):
            try:
                r = sessao.get(URL.format(cc=cc), timeout=30)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                print(f"[{cc}] erro: {e}; nova tentativa em {5 * (tentativa + 1)}s", flush=True)
                time.sleep(5 * (tentativa + 1))
        else:
            print(f"[{cc}] falhou 3 vezes, pulando", flush=True)
            continue
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(r.text)
        baixadas += 1
        print(f"{i}/{len(codigos)} {cc} ok", flush=True)
        time.sleep(PAUSA_SEGUNDOS)
    if baixadas:  # registra quando terminou a última coleta que baixou algo
        with open(os.path.join(cache, "_coletado_em.txt"), "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------- leitura das páginas

FIM_DO_BLOCO = ("Depending on where you live", "Note:", "Plan prices and extra member")


def ler_bloco_precos(html):
    """Retorna (nome da moeda, [linhas de texto do bloco de preços]) ou (None, []) se não houver."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    titulo = soup.find(lambda t: t.name in ("h2", "h3", "h4")
                       and t.get_text(strip=True).startswith("Pricing ("))
    if titulo is None:
        return None, []
    moeda = re.search(r"Pricing \((.+?)\)", titulo.get_text(" ", strip=True)).group(1).strip()
    linhas = []
    for el in titulo.find_all_next(["p", "h2", "h3", "h4"]):
        if el.name != "p":
            break
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if txt.startswith(FIM_DO_BLOCO):
            break
        if txt:
            linhas.append(txt)
    return moeda, linhas


RE_PLANO = re.compile(r"^(?P<plano>[^:]+?)\s*:\s*(?P<preco>.+?)\s*/\s*month", re.I)


def ler_planos(linhas):
    """[(plano, texto do preço)] - ignora as linhas de 'membro extra'."""
    planos = []
    for txt in linhas:
        if txt.lower().startswith("add "):
            continue
        m = RE_PLANO.match(txt)
        if m:
            # tira marcas de nota de rodapé ("Standard with ads *")
            planos.append((m.group("plano").strip().rstrip("*").strip(), m.group("preco").strip()))
    return planos


def numero(texto):
    """Converte '20,90', '8.99', '54.000', '7,000', '1.234,56' em float."""
    m = re.search(r"\d[\d.,\s]*\d|\d", texto)
    if not m:
        return None
    s = m.group(0).replace(" ", "").replace(" ", "")
    if "," in s and "." in s:  # o último separador é o decimal
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        return float(s.replace(mil, "").replace(dec, "."))
    sep = "," if "," in s else "." if "." in s else None
    if sep is None:
        return float(s)
    partes = s.split(sep)
    if len(partes) == 2 and len(partes[1]) != 3:  # 20,90 / 8.99 -> decimal
        return float(s.replace(sep, "."))
    return float(s.replace(sep, ""))  # 54.000 / 7,000 / 1,234,567 -> milhar


# ---------------------------------------------------------------- moeda, região, câmbio

# Nomes de moeda que a Netflix escreve diferente do padrão CLDR (babel). Completar se o
# processamento avisar de alguma moeda não reconhecida.
MOEDAS_MANUAIS = {
    "Arab Emirates Dirham": "AED",
    "US Dollars": "USD",
    "Canadian Dollars": "CAD",
    "Czech Crowns": "CZK",
}


def mapa_moedas():
    from babel import Locale
    mapa = {nome.lower(): cod for cod, nome in Locale("en").currencies.items()}
    mapa.update({k.lower(): v for k, v in MOEDAS_MANUAIS.items()})
    return mapa


def codigo_moeda(nome, precos_texto, mapa, cambio):
    """Código ISO da moeda: pelo nome do título; confere com um código escrito no preço (ex.: '59 ZAR')."""
    cod = mapa.get(nome.lower())
    escritos = {c for t in precos_texto for c in re.findall(r"\b[A-Z]{3}\b", t) if c in cambio}
    if cod is None and len(escritos) == 1:
        cod = escritos.pop()
    elif cod and escritos and escritos != {cod}:
        return None, f"moeda do título ({cod}) difere da escrita no preço ({','.join(sorted(escritos))})"
    return cod, None if cod else f"moeda não reconhecida: '{nome}'"


# Regiões usadas nos relatórios da Netflix: UCAN (EUA e Canadá), LATAM, EMEA e APAC.
# A Netflix não publica a lista de países de cada região; a classificação abaixo segue a
# geografia da ONU (M49). Os casos em que a região não é óbvia saem marcados como incertos.
INCERTOS = {
    "PR": "território dos EUA no Caribe (UCAN ou LATAM?)",
    "VI": "território dos EUA no Caribe (UCAN ou LATAM?)",
    "GU": "território dos EUA no Pacífico (UCAN ou APAC?)",
    "AS": "território dos EUA no Pacífico (UCAN ou APAC?)",
    "MP": "território dos EUA no Pacífico (UCAN ou APAC?)",
    "BM": "Bermuda (UCAN, LATAM ou EMEA?)",
    "GL": "Groenlândia (EMEA ou UCAN?)",
    "PM": "Saint-Pierre e Miquelon (EMEA ou UCAN?)",
}


def regiao(cc):
    import country_converter as coco
    cc = cc.upper()
    if cc in ("US", "CA"):
        return "UCAN", ""
    continente = coco.convert(names=cc, src="ISO2", to="continent", not_found=None)
    sub = coco.convert(names=cc, src="ISO2", to="UNregion", not_found=None)
    nota = INCERTOS.get(cc, "")
    if sub == "Central Asia":
        nota = "Ásia Central (APAC ou EMEA?)"
    if cc in ("BM", "GL", "PM"):
        return {"BM": "LATAM", "GL": "EMEA", "PM": "EMEA"}[cc], nota
    if continente == "America":
        return "LATAM", nota
    if continente in ("Europe", "Africa") or sub == "Western Asia":
        return "EMEA", nota
    if continente in ("Asia", "Oceania"):
        return "APAC", nota
    return "?", f"sem região (continente={continente}, sub-região={sub})"


# País = membro da ONU (193) + Vaticano, Palestina (observadores) e Taiwan. O resto é território.
PAISES_FORA_DA_ONU = {"VA", "PS", "TW"}


def tipo(cc):
    import country_converter as coco
    membro = coco.convert(names=cc, src="ISO2", to="UNmember", not_found=None)
    eh_membro = membro not in (None, "not found") and str(membro) != "nan"
    return "país" if eh_membro or cc in PAISES_FORA_DA_ONU else "território"


def obter_cambio(cache):
    """Câmbio do dia (unidades por 1 US$). Fica salvo no cache para a análise ser reprodutível."""
    caminho = os.path.join(cache, "_cambio.json")
    if not os.path.exists(caminho):
        r = requests.get(URL_CAMBIO, timeout=30)
        r.raise_for_status()
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(r.text)
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    return dados["rates"], dados["time_last_update_utc"]


# ---------------------------------------------------------------- processamento

def processar(cache, saida):
    import pycountry
    cambio, data_cambio = obter_cambio(cache)
    mapa = mapa_moedas()
    with open(os.path.join(cache, f"{CODIGO_INVALIDO}.html"), encoding="utf-8") as f:
        bloco_padrao = ler_bloco_precos(f.read())

    planos_csv, paises_csv, excluidos = [], [], []
    for pais in sorted(pycountry.countries, key=lambda p: p.alpha_2):
        cc = pais.alpha_2
        nome = getattr(pais, "common_name", pais.name)
        caminho = os.path.join(cache, f"{cc.lower()}.html")
        if not os.path.exists(caminho):
            excluidos.append(dict(cc=cc, pais=nome, motivo="página não baixada"))
            continue
        with open(caminho, encoding="utf-8") as f:
            bloco = ler_bloco_precos(f.read())
        moeda_nome, linhas = bloco
        if moeda_nome is None:
            excluidos.append(dict(cc=cc, pais=nome, motivo="página sem preços (Netflix indisponível?)"))
            continue
        if cc != "US" and bloco == bloco_padrao:
            excluidos.append(dict(cc=cc, pais=nome, motivo="página padrão (igual à de um código inválido)"))
            continue
        planos = ler_planos(linhas)
        if not planos:
            excluidos.append(dict(cc=cc, pais=nome, motivo=f"bloco de preços não reconhecido: {linhas[:3]}"))
            continue
        moeda, erro = codigo_moeda(moeda_nome, [p for _, p in planos], mapa, cambio)
        if erro or moeda not in cambio:
            excluidos.append(dict(cc=cc, pais=nome, motivo=erro or f"sem câmbio para {moeda}"))
            continue
        reg, nota_reg = regiao(cc)
        tp = tipo(cc)
        taxa = cambio[moeda]
        linhas_pais = []
        for plano, preco_txt in planos:
            valor = numero(preco_txt)
            usd = valor / taxa
            alerta = "" if 0.5 <= usd <= 40 else "preço em US$ fora do esperado - verificar"
            linhas_pais.append(dict(
                regiao=reg, regiao_incerta=nota_reg, tipo=tp, cc=cc, pais=nome, plano=plano,
                preco_texto=preco_txt, preco_local=valor, moeda=moeda, nome_moeda=moeda_nome,
                moeda_por_usd=taxa, preco_usd=round(usd, 2), alerta=alerta))
        planos_csv.extend(linhas_pais)
        basico = min(linhas_pais, key=lambda l: l["preco_local"])
        sem_mobile = [l for l in linhas_pais if l["plano"].lower() != "mobile"]
        basico_tv = min(sem_mobile, key=lambda l: l["preco_local"]) if sem_mobile else None
        paises_csv.append(dict(
            regiao=reg, regiao_incerta=nota_reg, tipo=tp, cc=cc, pais=nome, moeda=moeda,
            plano_mais_basico=basico["plano"], preco_local=basico["preco_local"],
            preco_usd=basico["preco_usd"],
            plano_mais_basico_sem_mobile=basico_tv["plano"] if basico_tv else "",
            preco_usd_sem_mobile=basico_tv["preco_usd"] if basico_tv else "",
            n_planos=len(linhas_pais), planos=" | ".join(f"{l['plano']}: {l['preco_texto']}" for l in linhas_pais),
            alerta="; ".join(sorted({l["alerta"] for l in linhas_pais if l["alerta"]}))))

    resumo = []
    escopos = (("só países", lambda p: p["tipo"] == "país"), ("países + territórios", lambda p: True))
    variantes = (("plano mais básico", "preco_usd"), ("mais básico sem Mobile", "preco_usd_sem_mobile"))
    for escopo, filtro in escopos:
        for variante, campo in variantes:
            for reg in ["UCAN", "LATAM", "EMEA", "APAC"]:
                da_regiao = [p for p in paises_csv if p["regiao"] == reg and filtro(p) and p[campo] != ""]
                if not da_regiao:
                    continue
                maior = max(da_regiao, key=lambda p: p[campo])
                menor = min(da_regiao, key=lambda p: p[campo])
                valores = [p[campo] for p in da_regiao]
                plano = "plano_mais_basico" if campo == "preco_usd" else "plano_mais_basico_sem_mobile"
                resumo.append(dict(
                    escopo=escopo, variante=variante, regiao=reg, n=len(da_regiao),
                    maior_pais=maior["pais"], maior_plano=maior[plano], maior_usd=maior[campo],
                    menor_pais=menor["pais"], menor_plano=menor[plano], menor_usd=menor[campo],
                    media_usd=round(statistics.mean(valores), 2), mediana_usd=round(statistics.median(valores), 2),
                    incertos_na_regiao=", ".join(p["pais"] for p in da_regiao if p["regiao_incerta"])))

    # Preço de cada tipo de plano em cada região (média simples entre países, sem ponderar por assinantes)
    por_tipo = []
    ordem = ["Mobile", "Basic", "Standard with ads", "Standard", "Premium"]
    for escopo, filtro in escopos:
        for reg in ["UCAN", "LATAM", "EMEA", "APAC"]:
            total = len({p["cc"] for p in planos_csv if p["regiao"] == reg and filtro(p)})
            for tipo_plano in ordem:
                da = [p for p in planos_csv if p["regiao"] == reg and filtro(p)
                      and p["plano"].replace("with adverts", "with ads") == tipo_plano]
                if not da:
                    continue
                v = [p["preco_usd"] for p in da]
                mn, mx = min(da, key=lambda p: p["preco_usd"]), max(da, key=lambda p: p["preco_usd"])
                por_tipo.append(dict(
                    escopo=escopo, regiao=reg, tipo_plano=tipo_plano,
                    paises_com_o_plano=len(da), paises_na_regiao=total,
                    media_usd=round(statistics.mean(v), 2), mediana_usd=round(statistics.median(v), 2),
                    min_usd=mn["preco_usd"], min_pais=mn["pais"], max_usd=mx["preco_usd"], max_pais=mx["pais"]))

    os.makedirs(saida, exist_ok=True)
    for nome_arq, linhas in (("netflix_todos_os_planos.csv", planos_csv),
                             ("netflix_plano_basico_por_pais.csv", paises_csv),
                             ("netflix_maior_menor_por_regiao.csv", resumo),
                             ("netflix_preco_por_tipo_e_regiao.csv", por_tipo),
                             ("netflix_paises_excluidos.csv", excluidos)):
        with open(os.path.join(saida, nome_arq), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)

    coletado = open(os.path.join(cache, "_coletado_em.txt")).read().strip()
    print(f"Páginas coletadas em: {coletado} (UTC) | câmbio: {data_cambio} (open.er-api.com)")
    print(f"Países com preço: {len(paises_csv)} | planos: {len(planos_csv)} | excluídos: {len(excluidos)}")
    for r in resumo:
        print(f"{r['escopo']:20} {r['variante']:23} {r['regiao']:6} n={r['n']:3} | "
              f"maior: {r['maior_pais']} US$ {r['maior_usd']:.2f} "
              f"({r['maior_plano']}) | menor: {r['menor_pais']} US$ {r['menor_usd']:.2f} ({r['menor_plano']}) | "
              f"média {r['media_usd']:.2f} | mediana {r['mediana_usd']:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("etapa", nargs="?", choices=["coletar", "processar", "tudo"], default="tudo")
    ap.add_argument("--cache", default="netflix_cache")
    ap.add_argument("--saida", default=".")
    args = ap.parse_args()
    if args.etapa in ("coletar", "tudo"):
        coletar(args.cache)
    if args.etapa in ("processar", "tudo"):
        processar(args.cache, args.saida)


if __name__ == "__main__":
    main()
