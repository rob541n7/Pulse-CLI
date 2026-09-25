/*
 * Pulse - IDX fundamentals & disclosures extractor (runs inside a normal browser tab).
 *
 * idx.co.id blocks non-browser clients, so this script runs in YOUR browser on an
 * idx.co.id page, reads the same JSON/XBRL the website itself uses, and saves one JSON
 * file you move to Pulse-CLI/data/fundamentals/.
 *
 * Usage (Chrome):
 *   1. Open https://www.idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/
 *   2. F12 -> Console, paste this whole file, Enter
 *   3. Run:  await pulseIdx.run()          // universe tickers below, saves pulse_idx_YYYYMMDD.json
 *      or:   await pulseIdx.run(["BBCA", "ASII"])
 *   4. Move the downloaded file to Pulse-CLI/data/fundamentals/ and run update_dashboard.bat
 *
 * Requests are sequential with a pause between them to stay polite to idx.co.id.
 * Progress is kept in localStorage: if the page reloads, paste the script again and re-run
 * `await pulseIdx.run()`; finished tickers are skipped.
 */
(() => {
  const DELAY_MS = 400;
  const INSTANT = [
    "Assets", "Liabilities", "Equity", "EquityAttributableToEquityOwnersOfParentEntity",
    "CurrentAssets", "CurrentLiabilities", "CashAndCashEquivalents", "ShortTermBankLoans", "LongTermBankLoans",
  ];
  const DURATION = [
    "SalesAndRevenue", "InterestIncome", "GrossProfit", "ProfitLossBeforeIncomeTax", "ProfitLoss",
    "ProfitLossAttributableToParentEntity", "NetCashFlowsReceivedFromUsedInOperatingActivities",
    "BasicEarningsLossPerShareFromContinuingOperations",
  ];
  const DEI = {
    currency: "DescriptionOfPresentationCurrency", end: "CurrentPeriodEndDate", type: "TypeOfReportOnFinancialStatements",
    sector: "Sector", subsector: "Subsector", industry: "Industry", opinion: "TypeOfAuditorsOpinion",
  };
  // Pengumuman penting (sisanya laporan rutin = noise)
  const EVENTS = [
    ["dividen", /dividen/i],
    ["rups", /rapat umum|rups/i],
    ["buyback", /pembelian kembali|buy ?back/i],
    ["rights_issue", /hmetd|right|penambahan modal|private placement|pmthmetd/i],
    ["transaksi_material", /transaksi material|akuisisi|pengambilalihan|penggabungan|merger|divestasi|penjualan dan pengalihan saham/i],
    ["afiliasi", /transaksi afiliasi|benturan kepentingan/i],
    ["kepemilikan", /perubahan kepemilikan|kepemilikan saham|pengendali/i],
    ["tender_offer", /penawaran tender|tender offer/i],
    ["penjelasan_bursa", /permintaan penjelasan|pemberitaan media|volatilitas|unusual/i],
    ["suspensi", /suspensi|penghentian sementara/i],
    ["stock_split", /pemecahan|stock split|penggabungan nilai nominal/i],
    ["laporan_keuangan", /penyampaian laporan keuangan/i],
  ];
  const NOISE = /registrasi pemegang efek|aktivitas eksplorasi|rencana penyampaian|laporan tahunan|keberlanjutan|esg|public expose|kurs konversi|pengalihan kembali saham/i;
  const DEFAULT_TICKERS = [
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII", "TPIA", "BRPT", "BBNI", "EMAS", "CUAN", "BRMS", "UNTR", "AADI", "IMPC",
    "ICBP", "ANTM", "MDKA", "ADRO", "BUMI", "UNVR", "INDF", "MBMA", "PTRO", "AMRT", "CPIN", "INCO", "INKP", "EXCL",
    "TAPG", "MEDC", "CMRY", "TINS", "KLBF", "PTBA", "PGAS", "GGRM", "ENRG", "AKRA", "ITMG", "EMTK", "JPFA", "TOWR",
    "BNBR", "SINI", "CBDK", "JSMR", "MAPA", "PACK", "INTP", "BUVA", "AUTO", "DSNG", "BBTN", "DEWA", "AALI", "RAJA",
    "INDY", "BFIN", "PWON", "CARE", "COIN", "BSDE", "ARTO", "HRUM", "ARKO", "BKSL", "SCMA", "RATU", "BUKA", "SMGR",
  ];

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function getJSON(url) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const res = await fetch(url);
      const text = await res.text();
      if (text.startsWith("{") || text.startsWith("[")) return JSON.parse(text);
      await sleep(1500 * (attempt + 1)); // 503 sesaat -> tunggu lalu ulang
    }
    throw new Error("Bukan JSON: " + url);
  }

  async function unzip(buf) {
    const dv = new DataView(buf), files = {};
    let eocd = buf.byteLength - 22;
    while (eocd >= 0 && dv.getUint32(eocd, true) !== 0x06054b50) eocd--;
    const n = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    for (let i = 0; i < n; i++) {
      const method = dv.getUint16(p + 10, true), csize = dv.getUint32(p + 20, true);
      const nlen = dv.getUint16(p + 28, true), elen = dv.getUint16(p + 30, true), clen = dv.getUint16(p + 32, true);
      const lho = dv.getUint32(p + 42, true);
      const name = new TextDecoder().decode(new Uint8Array(buf, p + 46, nlen));
      const start = lho + 30 + dv.getUint16(lho + 26, true) + dv.getUint16(lho + 28, true);
      const data = new Uint8Array(buf, start, csize);
      files[name] = method === 0 ? new TextDecoder().decode(data)
        : await new Response(new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).text();
      p += 46 + nlen + elen + clen;
    }
    return files;
  }

  async function loadReport(code, year, period) {
    const url = `/primary/ListedCompany/GetFinancialReport?indexFrom=1&pageSize=12&year=${year}&reportType=rdf` +
      `&EmitenType=s&periode=${period}&kodeEmiten=${code}&SortColumn=KodeEmiten&SortOrder=asc`;
    const r = await getJSON(url);
    const att = r.Results?.[0]?.Attachments?.find((a) => a.File_Name === "instance.zip");
    if (!att) return null;
    await sleep(DELAY_MS);
    const files = await unzip(await (await fetch(encodeURI(att.File_Path))).arrayBuffer());
    const xml = files[Object.keys(files).find((f) => f.endsWith(".xbrl"))];
    const doc = new DOMParser().parseFromString(xml, "application/xml");
    const facts = {};
    for (const el of doc.documentElement.children) {
      const ctx = el.getAttribute("contextRef");
      const tag = el.tagName.split(":").pop();
      if (ctx) facts[tag + "@" + ctx] = el.textContent.trim();
    }
    const num = (tag, ctx) => {
      const v = facts[tag + "@" + ctx];
      return v === undefined || v === "" || isNaN(Number(v)) ? null : Number(v);
    };
    const pick = (tags, ctx) => Object.fromEntries(tags.map((t) => [t, num(t, ctx)]));
    const dei = Object.fromEntries(Object.entries(DEI).map(([k, t]) => [k, facts[t + "@CurrentYearInstant"] || null]));
    return {
      year, period: period.toUpperCase(), modified: att.File_Modified, ...dei,
      instant: pick(INSTANT, "CurrentYearInstant"),
      current: pick(DURATION, "CurrentYearDuration"),
      prior: pick(DURATION, "PriorYearDuration"),
    };
  }

  async function latestReport(code, year) {
    for (const [y, p] of [[year, "tw3"], [year, "tw2"], [year, "tw1"], [year - 1, "audit"], [year - 1, "tw3"]]) {
      const r = await loadReport(code, y, p);
      await sleep(DELAY_MS);
      if (r) return r;
    }
    return null;
  }

  async function fundamentals(code, year = new Date().getFullYear()) {
    const latest = await latestReport(code, year);
    if (!latest) return { code, error: "laporan tidak ditemukan" };
    // Laporan tahunan terakhir untuk TTM = FY + YTD berjalan - YTD tahun lalu
    const fy = latest.period === "AUDIT" ? null : await loadReport(code, latest.year - 1, "audit");
    return { code, latest, fy: fy && { year: fy.year, current: fy.current, instant: fy.instant, currency: fy.currency } };
  }

  async function announcements(code, since) {
    const r = await getJSON(`/primary/ListedCompany/GetAnnouncement?kodeEmiten=${code}&emitenType=*&indexFrom=0` +
      `&pageSize=100&dateFrom=${since}&dateTo=&lang=id&keyword=`);
    const out = [];
    for (const x of r.Replies || []) {
      const title = (x.pengumuman.JudulPengumuman || "").trim();
      if (NOISE.test(title)) continue;
      const cat = EVENTS.find(([, re]) => re.test(title));
      if (!cat) continue;
      const pdf = (x.attachments || []).find((a) => !a.IsAttachment) || x.attachments?.[0];
      out.push({ date: x.pengumuman.TglPengumuman.slice(0, 10), category: cat[0], title,
                 url: pdf?.FullSavePath || null });
    }
    return out;
  }

  // Progres disimpan di localStorage per hari: kalau halaman reload, jalankan lagi dan proses lanjut.
  const storageKey = () => `pulse_idx_${new Date().toISOString().slice(0, 10).replaceAll("-", "")}`;

  async function collect(codes = DEFAULT_TICKERS, { days = 90, onProgress = console.log } = {}) {
    const since = new Date(Date.now() - days * 864e5).toISOString().slice(0, 10).replaceAll("-", "");
    let result = null;
    try { result = JSON.parse(localStorage.getItem(storageKey())); } catch (e) { /* abaikan */ }
    result = result || { source: "idx.co.id (XBRL instance & pengumuman)", since, fundamentals: {}, announcements: {} };
    for (const [i, code] of codes.entries()) {
      if (result.fundamentals[code] && !result.fundamentals[code].error && result.announcements[code]) continue;
      try {
        result.fundamentals[code] = await fundamentals(code);
        result.announcements[code] = await announcements(code, result.since);
      } catch (e) {
        result.fundamentals[code] = { code, error: String(e) };
      }
      try { localStorage.setItem(storageKey(), JSON.stringify(result)); } catch (e) { /* kuota penuh: lanjut tanpa simpan */ }
      onProgress(`${i + 1}/${codes.length} ${code}`);
      await sleep(DELAY_MS);
    }
    result.generated = new Date().toISOString();
    return result;
  }

  async function run(codes = DEFAULT_TICKERS, opts = {}) {
    const data = await collect(codes, opts);
    const name = `pulse_idx_${new Date().toISOString().slice(0, 10).replaceAll("-", "")}.json`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: "application/json" }));
    a.download = name;
    a.click();
    try { localStorage.removeItem(storageKey()); } catch (e) { /* abaikan */ }
    return `Tersimpan: ${name} (${codes.length} saham)`;
  }

  window.pulseIdx = { collect, run, fundamentals, announcements, DEFAULT_TICKERS };
  return "pulseIdx siap. Jalankan: await pulseIdx.run()";
})();
