"""Gráfico de dispersão: Índice de bem-estar de Sen vs. Índice de Liberdade Econômica (Heritage).

Índice de bem-estar de Sen (Sen, 1976):  W = μ · (1 − G)
    μ = PIB per capita, PPC (US$ internacionais constantes de 2021) — Banco Mundial, NY.GDP.PCAP.PP.KD
    G = coeficiente de Gini (0–1)                                     — Banco Mundial, SI.POV.GINI

Eixo X: pontuação geral ("Overall Score") do Index of Economic Freedom da Heritage Foundation.
Esses dados não são baixados automaticamente: exporte o CSV em https://www.heritage.org/index/
e passe o caminho com --heritage.

Uso:
    python sen_vs_heritage.py --heritage heritage.csv
    python sen_vs_heritage.py --heritage heritage.csv --year 2025 --label-all
"""

import argparse
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

WB_API = "https://api.worldbank.org/v2"
GDP_PPP = "NY.GDP.PCAP.PP.KD"
GINI = "SI.POV.GINI"

# Nomes usados por outras fontes (ex.: Heritage) que não batem com os do Banco Mundial.
ALIASES = {
    "bahamas": "BHS",
    "brunei": "BRN",
    "burma": "MMR",
    "myanmar": "MMR",
    "cabo verde": "CPV",
    "cape verde": "CPV",
    "congo democratic republic of the": "COD",
    "democratic republic of the congo": "COD",
    "congo republic of": "COG",
    "republic of congo": "COG",
    "cote d ivoire": "CIV",
    "ivory coast": "CIV",
    "czech republic": "CZE",
    "czechia": "CZE",
    "egypt": "EGY",
    "eswatini": "SWZ",
    "swaziland": "SWZ",
    "gambia": "GMB",
    "the gambia": "GMB",
    "hong kong": "HKG",
    "iran": "IRN",
    "korea south": "KOR",
    "south korea": "KOR",
    "korea north": "PRK",
    "north korea": "PRK",
    "kyrgyz republic": "KGZ",
    "kyrgyzstan": "KGZ",
    "laos": "LAO",
    "macau": "MAC",
    "macao": "MAC",
    "micronesia": "FSM",
    "north macedonia": "MKD",
    "macedonia": "MKD",
    "russia": "RUS",
    "saint lucia": "LCA",
    "saint vincent and the grenadines": "VCT",
    "slovakia": "SVK",
    "slovak republic": "SVK",
    "syria": "SYR",
    "taiwan": "TWN",
    "turkey": "TUR",
    "turkiye": "TUR",
    "venezuela": "VEN",
    "vietnam": "VNM",
    "viet nam": "VNM",
    "yemen": "YEM",
}


def norm(name: str) -> str:
    """Normaliza nomes de países para comparação (sem acentos, pontuação ou caixa)."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def wb_get(path: str) -> list:
    url = f"{WB_API}/{path}{'&' if '?' in path else '?'}format=json&per_page=20000"
    with urllib.request.urlopen(url, timeout=60) as r:
        payload = json.load(r)
    if len(payload) < 2 or payload[1] is None:
        raise RuntimeError(f"Resposta inesperada do Banco Mundial: {payload[0]}")
    return payload[1]


def wb_countries() -> pd.DataFrame:
    """Países (exclui agregados regionais/de renda)."""
    rows = [
        {"iso3": c["id"], "wb_name": c["name"]}
        for c in wb_get("country")
        if c["region"]["value"] != "Aggregates"
    ]
    return pd.DataFrame(rows)


def wb_latest(indicator: str, start: int, end: int) -> pd.DataFrame:
    """Valor mais recente disponível de cada país dentro de [start, end]."""
    rows = [
        {"iso3": r["countryiso3code"], "year": int(r["date"]), "value": r["value"]}
        for r in wb_get(f"country/all/indicator/{indicator}?date={start}:{end}")
        if r["value"] is not None and r["countryiso3code"]
    ]
    df = pd.DataFrame(rows).sort_values("year")
    return df.groupby("iso3").tail(1).set_index("iso3")


def load_world_bank(start: int, end: int, cache: Path) -> pd.DataFrame:
    if cache.exists():
        return pd.read_csv(cache)
    countries = wb_countries()
    gdp = wb_latest(GDP_PPP, start, end)
    gini = wb_latest(GINI, start, end)
    df = countries.set_index("iso3").join(
        gdp.rename(columns={"value": "pib_pc_ppc", "year": "ano_pib"}), how="inner"
    ).join(gini.rename(columns={"value": "gini", "year": "ano_gini"}), how="inner")
    df["sen"] = df["pib_pc_ppc"] * (1 - df["gini"] / 100)
    df = df.reset_index()
    df.to_csv(cache, index=False)
    return df


def pick_column(df: pd.DataFrame, explicit: str | None, patterns: list[str]) -> str:
    if explicit:
        return explicit
    for pat in patterns:
        for col in df.columns:
            if re.search(pat, str(col), re.I):
                return col
    sys.exit(f"Coluna não encontrada (procurei {patterns}). Colunas: {list(df.columns)}")


def load_heritage(path: Path, args) -> pd.DataFrame:
    df = pd.read_excel(path) if path.suffix.lower() in (".xls", ".xlsx") else pd.read_csv(path)
    country = pick_column(df, args.country_col, [r"^country", r"country", r"name"])
    score = pick_column(df, args.score_col, [r"overall", r"score"])
    year_col = args.year_col or next((c for c in df.columns if re.search(r"year", str(c), re.I)), None)
    if year_col is not None:
        year = args.year or int(pd.to_numeric(df[year_col], errors="coerce").max())
        df = df[pd.to_numeric(df[year_col], errors="coerce") == year]
        print(f"Heritage: usando o ano {year}")
    out = pd.DataFrame({
        "pais_heritage": df[country],
        "heritage": pd.to_numeric(df[score], errors="coerce"),
    }).dropna()
    return out


def match_iso3(heritage: pd.DataFrame, countries: pd.DataFrame) -> pd.DataFrame:
    lookup = {norm(n): iso for iso, n in zip(countries["iso3"], countries["wb_name"])}
    # Nomes do Banco Mundial costumam vir como "Korea, Rep." -> também indexa a parte antes da vírgula.
    for iso, n in zip(countries["iso3"], countries["wb_name"]):
        lookup.setdefault(norm(n.split(",")[0]), iso)
    lookup.update(ALIASES)
    heritage = heritage.copy()
    heritage["iso3"] = heritage["pais_heritage"].map(lambda n: lookup.get(norm(n)))
    missing = heritage.loc[heritage["iso3"].isna(), "pais_heritage"].tolist()
    if missing:
        print(f"Aviso: {len(missing)} país(es) da Heritage sem correspondência no Banco Mundial "
              f"(adicione em ALIASES se necessário): {', '.join(map(str, missing))}")
    return heritage.dropna(subset=["iso3"])


def plot(df: pd.DataFrame, out: Path, label_all: bool, log_y: bool, highlight: list[str]):
    surface, ink, ink2, series = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6"
    fig, ax = plt.subplots(figsize=(13, 8.5), facecolor=surface)
    ax.set_facecolor(surface)
    ax.scatter(df["heritage"], df["sen"], s=40, color=series, alpha=0.85,
               edgecolor=surface, linewidth=1.5, zorder=3)

    if label_all:
        to_label = df
    else:
        # Rótulos seletivos: extremos de cada eixo + países destacados.
        idx = set(df.nlargest(6, "sen").index) | set(df.nsmallest(6, "sen").index)
        idx |= set(df.nlargest(4, "heritage").index) | set(df.nsmallest(4, "heritage").index)
        idx |= set(df[df["iso3"].isin(highlight)].index)
        to_label = df.loc[sorted(idx)]
    for _, r in to_label.iterrows():
        bold = r["iso3"] in highlight
        ax.annotate(r["wb_name"], (r["heritage"], r["sen"]), xytext=(4, 3),
                    textcoords="offset points", fontsize=7.5 if label_all else 8.5,
                    color=ink if bold else ink2, fontweight="bold" if bold else "normal")

    if log_y:
        ax.set_yscale("log")
    fmt = plt.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    ax.yaxis.set_major_formatter(fmt)
    ax.yaxis.set_minor_formatter(fmt)
    ax.set_xlabel("Índice de Liberdade Econômica — Heritage Foundation (0–100)", color=ink2)
    ax.set_ylabel("Índice de bem-estar de Sen = PIB per capita PPC × (1 − Gini)\n"
                  "(US$ internacionais constantes de 2021" + (", escala log)" if log_y else ")"),
                  color=ink2)
    ax.set_title(f"Bem-estar de Sen vs. economia de mercado — {len(df)} países",
                 loc="left", fontsize=14, color=ink, pad=12)
    ax.grid(True, color="#e4e3df", linewidth=0.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c9c8c2")
    ax.tick_params(colors=ink2)
    fig.text(0.01, 0.01,
             "Fontes: Banco Mundial (NY.GDP.PCAP.PP.KD, SI.POV.GINI — valor mais recente de cada país "
             "no período); Heritage Foundation, Index of Economic Freedom.",
             fontsize=8, color=ink2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, dpi=150, facecolor=surface)
    print(f"Gráfico salvo em {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--heritage", type=Path, required=True, help="CSV/XLSX exportado do site da Heritage")
    p.add_argument("--year", type=int, help="Ano do índice Heritage (padrão: o mais recente no arquivo)")
    p.add_argument("--country-col"), p.add_argument("--score-col"), p.add_argument("--year-col")
    p.add_argument("--wb-start", type=int, default=2015, help="Primeiro ano aceito para PIB/Gini")
    p.add_argument("--wb-end", type=int, default=2025, help="Último ano aceito para PIB/Gini")
    p.add_argument("--cache", type=Path, default=Path("data/world_bank_sen.csv"))
    p.add_argument("--out", type=Path, default=Path("sen_vs_heritage.png"))
    p.add_argument("--label-all", action="store_true", help="Rotula todos os países")
    p.add_argument("--linear", action="store_true", help="Eixo Y linear (padrão: log)")
    p.add_argument("--highlight", default="BRA", help="ISO3 a destacar, separados por vírgula")
    args = p.parse_args()

    args.cache.parent.mkdir(parents=True, exist_ok=True)
    wb = load_world_bank(args.wb_start, args.wb_end, args.cache)
    heritage = match_iso3(load_heritage(args.heritage, args), wb[["iso3", "wb_name"]])
    df = heritage.merge(wb, on="iso3", how="inner")
    print(f"{len(df)} países com os três dados (Heritage, PIB PPC e Gini).")

    table = args.out.with_suffix(".csv")
    df.sort_values("sen", ascending=False).to_csv(table, index=False)
    print(f"Tabela salva em {table}")
    plot(df, args.out, args.label_all, not args.linear, args.highlight.split(","))


if __name__ == "__main__":
    main()
