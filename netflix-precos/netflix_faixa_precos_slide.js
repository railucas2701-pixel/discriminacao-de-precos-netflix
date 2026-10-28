// Slide: faixa de preço (mínimo a máximo) do plano mais básico da Netflix por região (6 regiões)
// A faixa é um gráfico NATIVO do PowerPoint (barras empilhadas): 1ª série invisível = mínimo,
// 2ª = mínimo até a mediana, 3ª = mediana até o máximo. "Editar dados" abre a planilha no Excel.
const fs = require("fs");
const JSZip = require("jszip");
const pptxgen = require("pptxgenjs");
// applyTheme (opcional) grava as cores do THEME no tema do arquivo. Vem do skill "pptx" do Claude;
// sem ele (variável APPLY_THEME_JS vazia) o slide sai com as cores do tema padrão do Office.
const applyTheme = process.env.APPLY_THEME_JS ? require(process.env.APPLY_THEME_JS).applyTheme : null;

const SAIDA = process.argv[2] || "netflix_faixa_precos_regiao.pptx";

const THEME = {
  name: "Netflix precos",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B0B0B", lt1: "FFFFFF", dk2: "52514E", lt2: "F0EFEC",
    accent1: "2A78D6", // azul forte: metade mais cara
    accent2: "86B6EF", // azul claro: metade mais barata
    accent3: "898781", // cinza: rótulos secundários
    accent4: "E1E0D9", // cinza claro: linhas finas
    accent5: "EB6834", accent6: "1BAF7A",
    hlink: "2A78D6", folHlink: "6250D6",
  },
};
const HEX = THEME.colors; // opções de gráfico só aceitam hex

// Só países (192), plano mais básico (o mais barato) de cada país, preços de 10/10/2026
const REGIOES = [
  { cod: "UCAN", nome: "EUA e Canadá", n: 2, med: 7.30,
    min: { v: 5.61, txt: "Canadá · Standard c/ anúncios" }, max: { v: 8.99, txt: "EUA · Standard c/ anúncios" } },
  { cod: "LATAM", nome: "América Latina e Caribe", n: 33, med: 5.99,
    min: { v: 3.99, txt: "Belize e mais 8 países · Básico" }, max: { v: 11.99, txt: "Uruguai e Trinidad e Tobago · Básico" } },
  { cod: "Europa", nome: "Inclui Turquia, Chipre e Cáucaso", n: 48, med: 9.93,
    min: { v: 5.27, txt: "Turquia · Básico" }, max: { v: 17.94, txt: "Suíça e Liechtenstein · Básico" } },
  { cod: "Oriente Médio", nome: "Países árabes da Ásia, Israel e Irã", n: 13, med: 7.99,
    min: { v: 3.99, txt: "Iraque, Irã e mais 4 países · Básico" }, max: { v: 10.74, txt: "Israel · Básico" } },
  { cod: "África", nome: "Continente inteiro", n: 54, med: 2.99,
    min: { v: 1.54, txt: "Quênia · Mobile" }, max: { v: 4.52, txt: "Marrocos · Básico" } },
  { cod: "APAC", nome: "Ásia-Pacífico", n: 42, med: 2.99,
    min: { v: 0.90, txt: "Paquistão · Mobile" }, max: { v: 12.48, txt: "Singapura · Básico" } },
];

const usd = (v) => "US$ " + v.toFixed(2).replace(".", ",");

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13,33" x 7,5"
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "Netflix: faixa de preço por região";
  const C = pres.SchemeColor;

  pres.defineSlideMaster({
    title: "Titulo e grafico",
    background: { color: C.background1 },
    margin: [0.5, 0.5, 0.5, 0.5],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.35, w: 12.33, h: 0.65,
          fontSize: 30, bold: true, color: C.text1, align: "left", valign: "top", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "subtitulo", type: "body", x: 0.5, y: 1.0, w: 12.33, h: 0.4,
          fontSize: 15, color: C.text2, valign: "top", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "fonte", type: "body", x: 0.5, y: 6.75, w: 12.33, h: 0.5,
          fontSize: 10, color: C.accent3, valign: "top", margin: 0 }, text: "" } },
    ],
  });

  pres.addSection({ title: "Preços por região" });
  const s = pres.addSlide({ masterName: "Titulo e grafico", sectionTitle: "Preços por região" });
  s.addText("Netflix: faixa de preço do plano mais básico por região", { placeholder: "title" });
  s.addText("Menor e maior preço entre os países de cada região, em US$ por mês (outubro de 2026)",
            { placeholder: "subtitulo" });
  s.addText(
    "Fonte: Central de Ajuda da Netflix (help.netflix.com), preços coletados em 10/10/2026; câmbio do mesmo dia " +
    "(open.er-api.com). Plano mais básico = o mais barato de cada país (Mobile, Básico ou Standard com anúncios). " +
    "192 países; territórios excluídos. Em alguns países o imposto é cobrado à parte.",
    { placeholder: "fonte" });

  // Colunas (polegadas)
  const COL = {
    regiao: { x: 0.5, w: 2.9 },
    paises: { x: 3.4, w: 0.7 },
    min: { x: 4.2, w: 2.3 },
    faixa: { x: 6.75, w: 3.75 },
    max: { x: 10.75, w: 2.08 },
  };
  const yCab = 1.55, hCab = 0.35;
  const yLinhas = yCab + hCab + 0.05, hLinha = 0.66;
  const hLinhas = REGIOES.length * hLinha, yFim = yLinhas + hLinhas;

  // Cabeçalho
  const cab = { fontSize: 12, bold: true, color: C.text2, margin: 0, valign: "bottom", isTextBox: true };
  s.addText("Região", { ...cab, x: COL.regiao.x, y: yCab, w: COL.regiao.w, h: hCab, objectName: "cab_regiao" });
  s.addText("Países", { ...cab, x: COL.paises.x, y: yCab, w: COL.paises.w, h: hCab, align: "center", objectName: "cab_paises" });
  s.addText("Menor preço", { ...cab, x: COL.min.x, y: yCab, w: COL.min.w, h: hCab, align: "right", objectName: "cab_min" });
  s.addText("Faixa de preço (US$/mês)", { ...cab, x: COL.faixa.x, y: yCab, w: COL.faixa.w, h: hCab, align: "center", objectName: "cab_faixa" });
  s.addText("Maior preço", { ...cab, x: COL.max.x, y: yCab, w: COL.max.w, h: hCab, objectName: "cab_max" });
  s.addShape(pres.shapes.LINE, { x: 0.5, y: yCab + hCab + 0.02, w: 12.33, h: 0,
    line: { color: C.text2, width: 1 }, objectName: "linha_cabecalho" });

  REGIOES.forEach((r, i) => {
    const y = yLinhas + i * hLinha;
    if (i > 0) s.addShape(pres.shapes.LINE, { x: 0.5, y, w: 12.33, h: 0,
      line: { color: C.accent4, width: 0.75 }, objectName: `separador_${i}` });
    const caixa = { y: y + 0.04, h: hLinha - 0.08, margin: 0, valign: "middle", isTextBox: true };
    s.addText([
      { text: r.cod, options: { fontSize: 17, bold: true, color: C.text1, breakLine: true } },
      { text: r.nome, options: { fontSize: 10, color: C.accent3 } },
    ], { ...caixa, x: COL.regiao.x, w: COL.regiao.w, objectName: `regiao_${i}` });
    s.addText(String(r.n), { ...caixa, x: COL.paises.x, w: COL.paises.w, fontSize: 16, color: C.text1,
      align: "center", objectName: `paises_${i}` });
    const celula = (lado, d, x, w, align) => s.addText([
      { text: usd(d.v), options: { fontSize: 17, bold: true, color: C.text1, breakLine: true } },
      { text: d.txt, options: { fontSize: 10, color: C.accent3 } },
    ], { ...caixa, x, w, align, objectName: `${lado}_${i}` });
    celula("min", r.min, COL.min.x, COL.min.w, "right");
    celula("max", r.max, COL.max.x, COL.max.w, "left");
  });

  // Gráfico nativo de barras empilhadas. Em gráfico de barras horizontais a 1ª categoria fica
  // embaixo, então os dados entram em ordem invertida para a ordem bater com a tabela.
  const inv = [...REGIOES].reverse();
  const rotulos = inv.map((r) => r.cod);
  const folga = 0.25, hEixo = 0.3; // espaço para os rótulos do eixo (US$ 0 e 20 nas pontas)
  const chartW = COL.faixa.w + 2 * folga, chartH = hLinhas + hEixo;
  s.addChart(pres.charts.BAR, [
    { name: "Mínimo (invisível)", labels: rotulos, values: inv.map((r) => r.min.v) },
    { name: "Metade mais barata dos países", labels: rotulos, values: inv.map((r) => +(r.med - r.min.v).toFixed(2)) },
    { name: "Metade mais cara dos países", labels: rotulos, values: inv.map((r) => +(r.max.v - r.med).toFixed(2)) },
  ], {
    x: COL.faixa.x - folga, y: yLinhas, w: chartW, h: chartH,
    objectName: "grafico_faixa",
    barDir: "bar", barGrouping: "stacked", barGapWidthPct: 160,
    chartColors: ["FFFFFF", HEX.accent2, HEX.accent1],
    layout: { x: folga / chartW, y: 0, w: COL.faixa.w / chartW, h: hLinhas / chartH },
    catAxisHidden: true, catGridLine: { style: "none" },
    valAxisMinVal: 0, valAxisMaxVal: 20, valAxisMajorUnit: 5,
    valAxisLabelFontFace: "+mn-lt", valAxisLabelFontSize: 10, valAxisLabelColor: HEX.accent3,
    valAxisLineShow: false,
    valGridLine: { color: HEX.accent4, size: 0.75 },
    showLegend: false, showValue: false, showTitle: false,
  });

  // Legenda manual (a nativa listaria a série invisível)
  const yLeg = yFim + hEixo + 0.05;
  const legenda = [["Metade mais barata dos países", C.accent2], ["Metade mais cara dos países", C.accent1]];
  let xLeg = COL.faixa.x - 0.6;
  legenda.forEach(([txt, cor], k) => {
    s.addShape(pres.shapes.RECTANGLE, { x: xLeg, y: yLeg + 0.05, w: 0.16, h: 0.16, fill: { color: cor },
      line: { type: "none" }, objectName: `legenda_cor_${k}` });
    s.addText(txt, { x: xLeg + 0.22, y: yLeg, w: 2.2, h: 0.26, fontSize: 10, color: C.text2, margin: 0,
      valign: "middle", isTextBox: true, objectName: `legenda_txt_${k}` });
    xLeg += 2.35;
  });
  s.addText("a troca de cor marca a mediana", { x: xLeg, y: yLeg, w: 2.2, h: 0.26, fontSize: 10, italic: true,
    color: C.accent3, margin: 0, valign: "middle", isTextBox: true, objectName: "legenda_mediana" });

  s.addNotes(
    "Faixa = menor e maior preço do plano mais básico entre os países de cada região (só países, sem territórios); " +
    "a troca de cor na barra é a mediana. Medianas: UCAN 7,30; LATAM 5,99; Europa 9,93; Oriente Médio 7,99; África 2,99; " +
    "APAC 2,99 (US$/mês). Os mínimos de África (Quênia) e APAC (Paquistão) são planos Mobile, que só funcionam no " +
    "celular; sem o Mobile, o mínimo da África é o Egito (US$ 2,10) e o de APAC continua o Paquistão (US$ 1,63, Básico). " +
    "Regiões: África = continente inteiro; Europa inclui Turquia, Chipre e Cáucaso (classificação do Banco Mundial); " +
    "Oriente Médio = países árabes da Ásia, Israel e Irã. A Netflix não publica a lista de países de cada região."
  );

  await pres.writeFile({ fileName: SAIDA });
  await tornarPrimeiraSerieInvisivel(SAIDA);
  if (applyTheme) await applyTheme(SAIDA, THEME);
  else console.warn("aviso: APPLY_THEME_JS não definido; slide gerado com o tema padrão do Office");
  console.log("ok:", SAIDA);
}

// pptxgenjs não deixa uma série sem preenchimento: troca o preenchimento da 1ª série por noFill
async function tornarPrimeiraSerieInvisivel(arquivo) {
  const zip = await JSZip.loadAsync(fs.readFileSync(arquivo));
  const nomes = Object.keys(zip.files).filter((n) => /^ppt\/charts\/chart\d+\.xml$/.test(n));
  if (nomes.length !== 1) throw new Error("esperava 1 gráfico, achei " + nomes.length);
  let xml = await zip.file(nomes[0]).async("string");
  const ini = xml.indexOf("<c:ser>"), fim = xml.indexOf("</c:ser>", ini);
  const ser = xml.slice(ini, fim);
  const a = ser.indexOf("<c:spPr>"), b = ser.indexOf("</c:spPr>", a) + "</c:spPr>".length;
  if (a < 0 || b < a) throw new Error("spPr da 1ª série não encontrado");
  const nova = ser.slice(0, a) + "<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>" + ser.slice(b);
  xml = xml.slice(0, ini) + nova + xml.slice(fim);
  zip.file(nomes[0], xml);
  fs.writeFileSync(arquivo, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

main().catch((e) => { console.error(e); process.exit(1); });
