"""
Peso do preço da Netflix no orçamento das famílias, por país e região.

    % do consumo = preço mensal em US$ ÷ (consumo das famílias per capita em US$ ÷ 12)

Consumo das famílias per capita = consumo final das famílias (US$ correntes, Banco Mundial
NE.CON.PRVT.CD) ÷ população (SP.POP.TOTL), no ano mais recente em que os dois existem.

Réguas de "espaço para aumento" (nenhuma usa os EUA):
  - pares de renda: mediana do % entre países do mesmo grupo de renda do Banco Mundial;
  - curva da Netflix: regressão ln(preço) = a + b·ln(consumo) entre todos os países; o resíduo
    mostra quanto o país está acima/abaixo do preço que a Netflix cobra de países parecidos.

Entrada: CSVs gerados pelo netflix_scraper.py (pasta resultado_netflix).
Saída (na mesma pasta): netflix_preco_vs_consumo_por_pais.csv, netflix_preco_vs_consumo_por_regiao.csv,
  netflix_curva_preco_standard.png e netflix_curva_preco_basico.png.
Requer: pip install requests matplotlib

Uso:
  python netflix_acessibilidade.py [--entrada resultado_netflix] [--cache netflix_cache]
"""
import argparse
import csv
import json
import math
import os
import statistics

import requests

API = "https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&date={anos}&per_page=20000"
ANOS = "2018:2026"
INDICADORES = {
    "consumo": "NE.CON.PRVT.CD",  # consumo final das famílias, US$ correntes
    "populacao": "SP.POP.TOTL",
    "cambio_ano": "PA.NUS.FCRF",  # câmbio oficial, moeda local por US$, média do ano
    "pib_pc": "NY.GDP.PCAP.CD",  # PIB per capita, US$ correntes (só para estimar consumo que falta)
}


def baixar_indicador(ind, cache):
    caminho = os.path.join(cache, f"_bm_{ind}.json")
    if not os.path.exists(caminho):
        r = requests.get(API.format(ind=ind, anos=ANOS), timeout=60)
        r.raise_for_status()
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(r.text)
    with open(caminho, encoding="utf-8") as f:
        meta, registros = json.load(f)
    if int(meta.get("pages", 1)) > 1:
        raise SystemExit(f"{ind}: resposta em {meta['pages']} páginas; aumente per_page")
    # {ISO2: {ano: valor}}
    dados = {}
    for r in registros or []:
        if r.get("value") is None:
            continue
        dados.setdefault(r["country"]["id"], {})[int(r["date"])] = float(r["value"])
    return dados


def baixar_grupos_de_renda(cache):
    """{ISO2: grupo de renda do Banco Mundial (Low/Lower middle/Upper middle/High income)}."""
    caminho = os.path.join(cache, "_bm_paises.json")
    if not os.path.exists(caminho):
        r = requests.get("https://api.worldbank.org/v2/country?format=json&per_page=400", timeout=60)
        r.raise_for_status()
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(r.text)
    with open(caminho, encoding="utf-8") as f:
        meta, paises = json.load(f)
    if int(meta.get("pages", 1)) > 1:
        raise SystemExit(f"lista de países em {meta['pages']} páginas; aumente per_page")
    return {p["iso2Code"]: p["incomeLevel"]["value"] for p in paises
            if p.get("incomeLevel", {}).get("id") not in (None, "", "NA")}


# Cores e tinta (paleta de referência, modo claro)
SUPERFICIE, TINTA, TINTA_2, TINTA_MUDA = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRADE, CONTEXTO, DESTAQUE = "#e1e0d9", "#c3c2b7", "#2a78d6"


def grafico(linhas, regressao, plano, caminho):
    """4 painéis (um por região): cada ponto é um país; a reta é o padrão de preço da Netflix."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator

    preco_col = f"preco_{plano}_usd"
    espaco_col = f"espaco_{plano}_vs_curva"
    a, b, r2 = regressao[plano]
    xs = [l["consumo_pc_mensal_usd"] for l in linhas]
    ys = [l[preco_col] for l in linhas]
    x_reta = [min(xs) * 0.9, max(xs) * 1.1]
    y_reta = [math.exp(a + b * math.log(x)) for x in x_reta]

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9})
    fig, eixos = plt.subplots(2, 2, figsize=(11, 8.5), dpi=200, sharex=True, sharey=True,
                              facecolor=SUPERFICIE)
    nome_plano = "Standard" if plano == "standard" else "plano mais básico"
    fig.suptitle(f"Preço do {nome_plano} da Netflix × consumo das famílias por pessoa",
                 x=0.06, ha="left", fontsize=13, fontweight="bold", color=TINTA)
    fig.text(0.06, 0.935,
             f"Cada ponto é um país (azul = países da região; cinza = demais). A linha é o padrão de preço da "
             f"Netflix: ln(preço) = {a:.2f} + {b:.2f}·ln(consumo), R² = {r2:.2f}.\n"
             f"Abaixo da linha = mais barato que países com consumo parecido (indício de espaço para aumento). "
             f"Entre parênteses: quanto o preço teria que mudar para chegar à linha.",
             ha="left", va="top", fontsize=8.5, color=TINTA_2)

    for ax, reg in zip(eixos.flat, ["UCAN", "LATAM", "EMEA", "APAC"]):
        ax.set_facecolor(SUPERFICIE)
        da = [l for l in linhas if l["regiao"] == reg]
        outros = [l for l in linhas if l["regiao"] != reg]
        ax.scatter([l["consumo_pc_mensal_usd"] for l in outros], [l[preco_col] for l in outros],
                   s=14, color=CONTEXTO, edgecolors=SUPERFICIE, linewidths=0.8, zorder=2)
        ax.plot(x_reta, y_reta, color=TINTA_2, linewidth=1.5, zorder=3)
        ax.scatter([l["consumo_pc_mensal_usd"] for l in da], [l[preco_col] for l in da],
                   s=40, color=DESTAQUE, edgecolors=SUPERFICIE, linewidths=1.2, zorder=4)

        # rótulos seletivos: os 2 mais abaixo e os 2 mais acima da linha (ou todos, se forem poucos)
        # escolhe até 2 países mais abaixo e 2 mais acima da linha, pulando pontos colados a um já
        # rotulado (países com preço e consumo quase iguais geram rótulos sobrepostos)
        lx = (math.log(min(xs)), math.log(max(xs)))
        ly = (math.log(min(ys)), math.log(max(ys)))

        def pos(l):
            return ((math.log(l["consumo_pc_mensal_usd"]) - lx[0]) / (lx[1] - lx[0]),
                    (math.log(l[preco_col]) - ly[0]) / (ly[1] - ly[0]))

        rotular = []
        ordenados = sorted(da, key=lambda l: l[espaco_col], reverse=True)
        for candidatos in (ordenados, ordenados[::-1]):
            escolhidos = 0
            for l in candidatos:
                if escolhidos == 2 or l in rotular:
                    break
                px, py = pos(l)
                if all(abs(px - qx) > 0.35 or abs(py - qy) > 0.06 for qx, qy in map(pos, rotular)):
                    rotular.append(l)
                    escolhidos += 1
        x_meio = math.sqrt(min(xs) * max(xs))  # ponto do meio do eixo (escala log)
        for l in rotular:
            nome = l["pais"].split(",")[0]
            a_direita = l["consumo_pc_mensal_usd"] < x_meio  # pontos à direita levam o rótulo à esquerda
            ax.annotate(f"{nome} ({l[espaco_col]:+.0%})",
                        (l["consumo_pc_mensal_usd"], l[preco_col]), xytext=(6 if a_direita else -6, 5),
                        textcoords="offset points", ha="left" if a_direita else "right",
                        fontsize=7.5, color=TINTA_2, zorder=5,
                        bbox=dict(boxstyle="round,pad=0.15", fc=SUPERFICIE, ec="none", alpha=0.85))

        med = statistics.median(l[espaco_col] for l in da)
        ax.set_title(f"{reg} · {len(da)} países · espaço mediano vs. linha: {med:+.0%}",
                     loc="left", fontsize=10, color=TINTA, fontweight="bold")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.xaxis.set_major_locator(FixedLocator([10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]))
        ax.yaxis.set_major_locator(FixedLocator([1, 2, 3, 5, 10, 20, 30, 50]))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(lambda v, _: f"${v / 1000:g}k" if v >= 1000 else f"${v:g}")
        ax.yaxis.set_major_formatter(lambda v, _: f"${v:g}")
        ax.grid(True, color=GRADE, linewidth=0.6, zorder=0)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color(CONTEXTO)
        ax.tick_params(colors=TINTA_MUDA, length=0, labelsize=8)

    for ax in eixos[1]:
        ax.set_xlabel("Consumo das famílias por pessoa, por mês (US$)", color=TINTA_2, fontsize=8.5)
    for ax in eixos[:, 0]:
        ax.set_ylabel(f"Preço do {nome_plano} (US$/mês)", color=TINTA_2, fontsize=8.5)
    fig.tight_layout(rect=(0.04, 0.02, 0.98, 0.90))
    fig.savefig(caminho, facecolor=SUPERFICIE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="resultado_netflix")
    ap.add_argument("--cache", default="netflix_cache")
    args = ap.parse_args()

    bm = {k: baixar_indicador(ind, args.cache) for k, ind in INDICADORES.items()}
    with open(os.path.join(args.cache, "_cambio.json"), encoding="utf-8") as f:
        cambio_hoje = json.load(f)["rates"]

    paises = [p for p in csv.DictReader(open(os.path.join(args.entrada, "netflix_plano_basico_por_pais.csv"),
                                             encoding="utf-8")) if p["tipo"] == "país"]
    planos = list(csv.DictReader(open(os.path.join(args.entrada, "netflix_todos_os_planos.csv"), encoding="utf-8")))
    standard = {p["cc"]: float(p["preco_usd"]) for p in planos if p["plano"] == "Standard"}

    grupos = baixar_grupos_de_renda(args.cache)
    pib_pc = bm["pib_pc"]

    # Consumo per capita: dado do Banco Mundial quando existe. Quando falta, estimativa =
    # PIB per capita × (consumo/PIB mediano dos países do mesmo grupo de renda).
    consumo_real = {}
    for p in paises:
        cons, pop = bm["consumo"].get(p["cc"], {}), bm["populacao"].get(p["cc"], {})
        anos = sorted(set(cons) & set(pop))
        if anos:
            consumo_real[p["cc"]] = (anos[-1], cons[anos[-1]] / pop[anos[-1]])
    razoes = {}
    for cc, (ano, c_pc) in consumo_real.items():
        if ano in pib_pc.get(cc, {}):
            razoes.setdefault(grupos.get(cc), []).append(c_pc / pib_pc[cc][ano])
    razao_grupo = {g: statistics.median(v) for g, v in razoes.items()}

    linhas, sem_dado = [], []
    for p in paises:
        cc = p["cc"]
        if cc in consumo_real:
            ano, consumo_pc = consumo_real[cc]
            fonte = "Banco Mundial"
        elif pib_pc.get(cc) and grupos.get(cc) in razao_grupo:
            ano = max(pib_pc[cc])
            consumo_pc = pib_pc[cc][ano] * razao_grupo[grupos[cc]]
            fonte = f"estimado (PIB per capita × {razao_grupo[grupos[cc]]:.0%}, mediana do grupo de renda)"
        else:
            sem_dado.append(p["pais"])
            continue
        mensal = consumo_pc / 12
        basico, std = float(p["preco_usd"]), standard[cc]

        # O consumo está em US$ ao câmbio médio do ano do dado; o preço, ao câmbio de hoje.
        # Se a moeda local desvalorizou muito desde então, o % fica distorcido: marcamos.
        alerta = []
        if ano < 2024:
            alerta.append(f"dado de consumo antigo ({ano})")
        # compara a MOEDA LOCAL do país (não a moeda de cobrança da Netflix, que às vezes é US$ ou €)
        from babel.numbers import get_territory_currencies
        locais = [m for m in get_territory_currencies(cc) if m != "USD"] or ["USD"]
        local = locais[0]
        fx_ano = bm["cambio_ano"].get(cc, {}).get(ano)
        if fx_ano and local != "USD" and local in cambio_hoje:
            desvalorizacao = 1 - fx_ano / cambio_hoje[local]  # >0: moeda local perdeu valor desde o ano do dado
            if not 0.2 <= fx_ano / cambio_hoje[local] <= 5:
                alerta.append(f"câmbio de {local} não comparável com {ano} (troca de moeda?)")
            elif abs(desvalorizacao) > 0.20:
                verbo = "desvalorizou" if desvalorizacao > 0 else "valorizou"
                alerta.append(f"{local} {verbo} {abs(desvalorizacao):.0%} frente ao US$ desde {ano}")
        linhas.append(dict(
            regiao=p["regiao"], regiao_incerta=p["regiao_incerta"], cc=cc, pais=p["pais"],
            grupo_renda=grupos.get(cc, "sem classificação"), fonte_consumo=fonte,
            ano_consumo=ano, consumo_pc_anual_usd=round(consumo_pc), consumo_pc_mensal_usd=round(mensal, 2),
            plano_mais_basico=p["plano_mais_basico"], preco_basico_usd=basico,
            pct_consumo_basico=round(100 * basico / mensal, 3),
            preco_standard_usd=std, pct_consumo_standard=round(100 * std / mensal, 3),
            alerta="; ".join(alerta)))

    # Réguas de comparação (nenhuma usa os EUA como referência):
    # 1) Pares de renda: mediana do % do consumo entre países do mesmo grupo de renda do Banco Mundial.
    # 2) Curva da própria Netflix: regressão ln(preço) = a + b·ln(consumo mensal) entre todos os países.
    #    "b" mostra quanto a Netflix sobe o preço quando a renda sobe 1%; o resíduo diz se o país está
    #    acima ou abaixo do preço que a Netflix cobra, em média, de países com o mesmo consumo.
    regressao = {}
    for c, preco in (("basico", "preco_basico_usd"), ("standard", "preco_standard_usd")):
        col = f"pct_consumo_{c}"
        med_grupo = {g: statistics.median(l[col] for l in linhas if l["grupo_renda"] == g)
                     for g in {l["grupo_renda"] for l in linhas}}
        x = [math.log(l["consumo_pc_mensal_usd"]) for l in linhas]
        y = [math.log(l[preco]) for l in linhas]
        b, a = statistics.linear_regression(x, y)
        regressao[c] = (a, b, statistics.correlation(x, y) ** 2)
        for l in linhas:
            pares = med_grupo[l["grupo_renda"]] / 100 * l["consumo_pc_mensal_usd"]
            curva = math.exp(a + b * math.log(l["consumo_pc_mensal_usd"]))
            l[f"espaco_{c}_vs_pares_de_renda"] = round(pares / l[preco] - 1, 3)
            l[f"preco_{c}_previsto_pela_curva_usd"] = round(curva, 2)
            l[f"espaco_{c}_vs_curva"] = round(curva / l[preco] - 1, 3)

    resumo = []
    for reg in ["UCAN", "LATAM", "EMEA", "APAC"]:
        da = [l for l in linhas if l["regiao"] == reg]
        for c in ("basico", "standard"):
            col = f"pct_consumo_{c}"
            v = sorted(l[col] for l in da)
            mn, mx = min(da, key=lambda l: l[col]), max(da, key=lambda l: l[col])
            resumo.append(dict(
                regiao=reg, plano=("mais básico" if c == "basico" else "Standard"), n=len(da),
                n_consumo_estimado=sum(1 for l in da if l["fonte_consumo"] != "Banco Mundial"),
                mediana_pct=round(statistics.median(v), 2), media_pct=round(statistics.mean(v), 2),
                p25_pct=round(v[len(v) // 4], 2) if len(v) >= 4 else "", p75_pct=round(v[(3 * len(v)) // 4], 2) if len(v) >= 4 else "",
                menor_peso=f"{mn['pais']} ({mn[col]:.2f}%)", maior_peso=f"{mx['pais']} ({mx[col]:.2f}%)",
                espaco_mediano_vs_pares_de_renda=f"{statistics.median(l[f'espaco_{c}_vs_pares_de_renda'] for l in da):+.0%}",
                espaco_mediano_vs_curva=f"{statistics.median(l[f'espaco_{c}_vs_curva'] for l in da):+.0%}"))

    for nome, dados in (("netflix_preco_vs_consumo_por_pais.csv", linhas),
                        ("netflix_preco_vs_consumo_por_regiao.csv", resumo)):
        with open(os.path.join(args.entrada, nome), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(dados[0].keys()))
            w.writeheader()
            w.writerows(dados)

    for plano in ("standard", "basico"):
        grafico(linhas, regressao, plano, os.path.join(args.entrada, f"netflix_curva_preco_{plano}.png"))

    print(f"Países com dado: {len(linhas)} | sem dado de consumo no Banco Mundial: {len(sem_dado)} {sem_dado}")
    for c, (a, b, r2) in regressao.items():
        print(f"Curva {c}: ln(preço) = {a:.2f} + {b:.2f}·ln(consumo mensal)  (R² = {r2:.2f})")
    for r in resumo:
        print(f"{r['regiao']:6} {r['plano']:12} n={r['n']:3} mediana {r['mediana_pct']:5.2f}% média {r['media_pct']:5.2f}% "
              f"| menor peso: {r['menor_peso']} | maior peso: {r['maior_peso']} "
              f"| espaço vs pares {r['espaco_mediano_vs_pares_de_renda']} | vs curva {r['espaco_mediano_vs_curva']}")


if __name__ == "__main__":
    main()
