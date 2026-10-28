"""
Teste da tese "a Netflix perde tempo de tela na TV para o YouTube" (EUA, Nielsen The Gauge).

Entrada: nielsen_gauge_transcrito.csv - fatia mensal do tempo total de TV (%), transcrita dos
infográficos mensais do The Gauge (nielsen.com), mai/2021 a jul/2026.

Quebras de metodologia da Nielsen (todas marcadas no gráfico):
  - até nov/2021: números publicados inteiros (sem decimal);
  - fev/2023: YouTube passa a ser só "YouTube Main" (sai o YouTube TV) e o streaming linear
    (vMVPD) sai da categoria streaming -> a série do YouTube cai ~0,7 p.p. artificialmente;
  - jun/2023: conteúdo original de streaming visto via decodificador passa de "outros" para streaming;
  - 2026: Nielsen avisa que The Gauge ainda não reflete sua nova "currency" e mudou a medição do Tubi.
Por isso os testes usam a janela de metodologia consistente: fev/2023 a jul/2026 (42 meses).

Testes:
  1. Tendência (p.p./ano) com efeito fixo de mês (tira a sazonalidade) e erro-padrão robusto (Newey-West).
  2. Variações em 12 meses: quando o YouTube ganha mais, a Netflix perde mais? (correlação/regressão)
  3. De onde veio o ganho do YouTube: comparação do mesmo mês em anos diferentes.

Uso: python netflix_youtube_atencao.py   (requer numpy e matplotlib)
"""
import csv
import math

import numpy as np

ARQ = "nielsen_gauge_transcrito.csv"
INICIO_CONSISTENTE = "2023-02"


def carregar():
    linhas = sorted(csv.DictReader(open(ARQ, encoding="utf-8")), key=lambda r: r["mes"])
    for r in linhas:
        for k in ("streaming", "cabo", "aberta", "outros", "youtube", "netflix"):
            r[k] = float(r[k])
        r["linear"] = r["cabo"] + r["aberta"]
        r["outros_streamings"] = r["streaming"] - r["youtube"] - r["netflix"]
        r["netflix_no_streaming"] = 100 * r["netflix"] / r["streaming"]
        r["youtube_no_streaming"] = 100 * r["youtube"] / r["streaming"]
    return linhas


def newey_west(X, residuos, defasagens=6):
    n = X.shape[0]
    XtX_inv = np.linalg.inv(X.T @ X)
    u = X * residuos[:, None]
    S = u.T @ u
    for l in range(1, defasagens + 1):
        w = 1 - l / (defasagens + 1)
        G = u[l:].T @ u[:-l]
        S += w * (G + G.T)
    return np.sqrt(np.diag(XtX_inv @ S @ XtX_inv))


def tendencia(linhas, coluna):
    """y = a + b*anos + efeitos fixos de mês. Retorna b (p.p./ano), erro-padrão HAC e n."""
    t = np.array([int(r["mes"][:4]) + (int(r["mes"][5:]) - 1) / 12 for r in linhas])
    meses = [int(r["mes"][5:]) for r in linhas]
    dummies = np.array([[1.0 if m == k else 0.0 for k in range(2, 13)] for m in meses])
    X = np.column_stack([np.ones(len(t)), t - t.mean(), dummies])
    y = np.array([r[coluna] for r in linhas])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    ep = newey_west(X, y - X @ beta)
    return beta[1], ep[1], len(y)


def variacoes_12m(linhas, coluna):
    por_mes = {r["mes"]: r for r in linhas}
    saida = {}
    for r in linhas:
        a, m = int(r["mes"][:4]), r["mes"][5:]
        anterior = f"{a - 1}-{m}"
        if anterior in por_mes:
            saida[r["mes"]] = r[coluna] - por_mes[anterior][coluna]
    return saida


def regressao_simples(x, y):
    x, y = np.array(x), np.array(y)
    X = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    ep = newey_west(X, y - X @ beta, defasagens=11)  # variações de 12 meses se sobrepõem
    return beta[1], ep[1], float(np.corrcoef(x, y)[0, 1])


def main():
    todas = carregar()
    janela = [r for r in todas if r["mes"] >= INICIO_CONSISTENTE]
    print(f"Série: {todas[0]['mes']} a {todas[-1]['mes']} ({len(todas)} meses); "
          f"janela consistente: {janela[0]['mes']} a {janela[-1]['mes']} ({len(janela)} meses)\n")

    print("1) TENDÊNCIA na janela consistente (p.p. por ano, sem sazonalidade; IC 95% robusto)")
    for col, nome in (("youtube", "YouTube (% do tempo de TV)"), ("netflix", "Netflix (% do tempo de TV)"),
                      ("linear", "TV aberta + cabo"), ("outros_streamings", "Outros streamings"),
                      ("netflix_no_streaming", "Netflix (% do tempo de streaming)"),
                      ("youtube_no_streaming", "YouTube (% do tempo de streaming)")):
        b, ep, n = tendencia(janela, col)
        print(f"   {nome:36} {b:+.2f} p.p./ano  [{b - 1.96 * ep:+.2f}; {b + 1.96 * ep:+.2f}]")

    print("\n2) VARIAÇÕES EM 12 MESES (mesmo mês do ano anterior), só pares dentro da janela consistente")
    d = {c: variacoes_12m(janela, c) for c in ("youtube", "netflix", "linear", "outros_streamings")}
    meses = sorted(d["youtube"])
    print(f"   {len(meses)} pares ({meses[0]} a {meses[-1]}); variações se sobrepõem -> poucos pontos independentes")
    for alvo, nome in (("netflix", "Netflix"), ("linear", "TV aberta + cabo"), ("outros_streamings", "Outros streamings")):
        b, ep, r = regressao_simples([d["youtube"][m] for m in meses], [d[alvo][m] for m in meses])
        print(f"   Δ{nome:18} vs ΔYouTube: correlação {r:+.2f} | inclinação {b:+.2f} (IC95% {b - 1.96 * ep:+.2f}; {b + 1.96 * ep:+.2f})")
    print("   (inclinação -1 = cada ponto que o YouTube ganha sai daquele grupo; 0 = sem relação)")

    print("\n3) DE ONDE VEIO O GANHO DO YOUTUBE (mesmo mês, anos diferentes, metodologia consistente)")
    por_mes = {r["mes"]: r for r in todas}
    for ini, fim in (("2023-07", "2026-07"), ("2023-02", "2026-02")):
        a, b = por_mes[ini], por_mes[fim]
        print(f"   {ini} -> {fim}: " + " | ".join(
            f"{n} {b[c] - a[c]:+.1f}" for c, n in (("youtube", "YouTube"), ("netflix", "Netflix"),
                                                     ("outros_streamings", "outros streamings"),
                                                     ("cabo", "cabo"), ("aberta", "aberta"), ("outros", "outros usos"))))

    grafico(todas)


def grafico(linhas):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import date

    SUP, TINTA, TINTA2, MUDA, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
    COR = {"youtube": "#2a78d6", "netflix": "#eb6834", "linear": "#1baf7a"}
    datas = [date(int(r["mes"][:4]), int(r["mes"][5:]), 15) for r in linhas]
    quebra = date(2023, 2, 1)

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.6), dpi=200, facecolor=SUP)
    fig.suptitle("Netflix × YouTube no tempo de TV dos EUA (Nielsen, The Gauge)", x=0.04, ha="left",
                 fontsize=13, fontweight="bold", color=TINTA)
    fig.text(0.04, 0.905, "Linha tracejada: fev/2023, quando a Nielsen tirou o YouTube TV da conta do YouTube "
                          "(antes, a série do YouTube é levemente inflada). Até nov/2021 os dados são inteiros.",
             fontsize=8.5, color=TINTA2, ha="left")

    def desenha(ax, series, titulo, ylabel):
        ax.set_facecolor(SUP)
        for col, nome in series:
            for trecho in ([i for i, d in enumerate(datas) if d < quebra], [i for i, d in enumerate(datas) if d >= quebra]):
                ax.plot([datas[i] for i in trecho], [linhas[i][col] for i in trecho], color=COR[col], linewidth=2)
            ax.annotate(f"{nome} {linhas[-1][col]:.1f}%", (datas[-1], linhas[-1][col]), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=TINTA)
        ax.axvline(quebra, color=MUDA, linewidth=1, linestyle=(0, (4, 3)))
        ax.set_title(titulo, loc="left", fontsize=10, fontweight="bold", color=TINTA)
        ax.set_ylabel(ylabel, color=TINTA2, fontsize=8.5)
        ax.grid(True, axis="y", color=GRADE, linewidth=0.6)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
        ax.tick_params(colors=MUDA, length=0, labelsize=8)
        ax.set_xticks([date(a, 1, 1) for a in range(2022, 2027)])
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_xlim(datas[0], date(2027, 6, 1))

    desenha(ax1, [("youtube", "YouTube"), ("netflix", "Netflix")],
            "Fatia do tempo total de TV", "% do tempo de TV")
    ax1.set_ylim(0, 16)
    # painel 2: % dentro do streaming
    for r in linhas:
        r["_yt"], r["_nf"] = r["youtube_no_streaming"], r["netflix_no_streaming"]
    COR["_yt"], COR["_nf"] = COR["youtube"], COR["netflix"]
    desenha(ax2, [("_yt", "YouTube"), ("_nf", "Netflix")],
            "Fatia dentro do tempo de streaming", "% do tempo de streaming")
    ax2.set_ylim(0, 35)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig("netflix_youtube_tempo_tv.png", facecolor=SUP)
    plt.close(fig)
    print("\nGráfico salvo em netflix_youtube_tempo_tv.png")


if __name__ == "__main__":
    main()
