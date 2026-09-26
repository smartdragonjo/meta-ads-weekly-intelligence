const state = { data: { ads: [], competitors: [], total_ads: 0, total_video_ads: 0, analyzed_video_ads: 0 }, filters: { competitor: "", type: "", platform: "" } };

const text = (value) => value === null || value === undefined || value === "" ? "—" : String(value);
const normalize = (value) => String(value || "").toLowerCase();
const typeOf = (ad) => {
  const value = normalize(`${ad.format} ${ad.media_type}`);
  if (value.includes("carousel")) return "carousel";
  if (value.includes("video")) return "video";
  if (value.includes("image") || value.includes("photo")) return "image";
  return normalize(ad.format) || "other";
};
const platforms = (ad) => String(ad.platforms || "").split(/[,|]/).map((item) => item.trim()).filter(Boolean);
const adBodyPreview = (ad) => {
  const raw = text(ad.ad_body || "");
  if (raw === "—") return "—";
  const plain = raw.replace(/\s+/g, " ").trim();
  return plain.length > 140 ? `${plain.slice(0, 140)}…` : plain;
};
const videoAnalysisBlock = (ad) => {
  if (!ad.video_url || !ad.analysis_status) return "";
  if (ad.analysis_status === "success") {
    const summary = ad.video_analysis?.summary || "—";
    const transcript = ad.video_analysis?.transcript || "—";
    const detail = ad.video_analysis?.confidence ? `<small>الثقة: ${text(ad.video_analysis.confidence)}</small>` : "";
    return `
      <section class="video-analysis">
        <h4>تحليل الفيديو</h4>
        <div class="analysis-item"><strong>ملخص الفيديو</strong><p>${text(summary).replace(/\n/g, "<br>")}</p></div>
        <div class="analysis-item"><strong>المحتوى الصوتي / التفريغ</strong><p>${text(transcript).replace(/\n/g, "<br>")}</p></div>
        ${detail}
      </section>
    `;
  }
  if (ad.analysis_status === "failed") {
    return `<section class="video-analysis failed"><h4>تحليل الفيديو</h4><p>تعذر تحليل الفيديو</p></section>`;
  }
  return "";
};

function setText(id, value) { const node = document.getElementById(id); if (node) node.textContent = text(value); }
function externalLink(url, label) {
  if (!url || !/^https?:\/\//i.test(url)) return "—";
  return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}
function filteredAds() {
  return state.data.ads.filter((ad) => {
    const matchesCompetitor = !state.filters.competitor || ad.page_name === state.filters.competitor;
    const matchesType = !state.filters.type || typeOf(ad) === state.filters.type;
    const matchesPlatform = !state.filters.platform || platforms(ad).includes(state.filters.platform);
    return matchesCompetitor && matchesType && matchesPlatform;
  });
}
function populateFilters() {
  const competitors = [...new Set(state.data.ads.map((ad) => ad.page_name).filter(Boolean))].sort();
  const platformValues = [...new Set(state.data.ads.flatMap(platforms))].sort();
  const addOptions = (id, values) => document.getElementById(id).insertAdjacentHTML("beforeend", values.map((value) => `<option value="${value}">${value}</option>`).join(""));
  addOptions("competitor-filter", competitors);
  addOptions("platform-filter", platformValues);
}
function renderAds() {
  const ads = filteredAds();
  document.getElementById("results-count").textContent = `${ads.length} إعلان`;
  const body = document.getElementById("ads-table-body");
  const mobile = document.getElementById("mobile-ads");
  body.innerHTML = ads.map((ad) => {
    const media = ad.video_url ? externalLink(ad.video_url, "فيديو") : externalLink(ad.image_url, "صورة");
    return `<tr tabindex="0" data-index="${state.data.ads.indexOf(ad)}"><td><strong>${text(ad.page_name)}</strong></td><td class="mono">${text(ad.ad_id)}</td><td>${text(ad.start_date)}</td><td>${text(typeOf(ad))}</td><td>${platforms(ad).join(" · ") || "—"}</td><td>${text(ad.cta)}</td><td>${adBodyPreview(ad)}</td><td class="link-stack">${externalLink(ad.ad_url, "الإعلان")} ${media}</td></tr>`;
  }).join("");
  mobile.innerHTML = ads.map((ad) => {
    const media = ad.video_url ? externalLink(ad.video_url, "فيديو") : externalLink(ad.image_url, "صورة");
    const analysisState = ad.analysis_status === "success" ? "تم التحليل" : ad.analysis_status === "failed" ? "فشل التحليل" : "غير متاح";
    return `
      <article class="mobile-ad-card" tabindex="0" data-index="${state.data.ads.indexOf(ad)}">
        <div class="mobile-ad-head"><strong>${text(ad.page_name)}</strong><span>${text(ad.ad_id)}</span></div>
        <dl>
          <div><dt>تاريخ الإعلان</dt><dd>${text(ad.start_date)}</dd></div>
          <div><dt>النوع</dt><dd>${text(typeOf(ad))}</dd></div>
          <div><dt>المنصات</dt><dd>${platforms(ad).join(" · ") || "—"}</dd></div>
          <div><dt>CTA</dt><dd>${text(ad.cta)}</dd></div>
          <div><dt>Caption</dt><dd>${adBodyPreview(ad)}</dd></div>
          <div><dt>تحليل الفيديو</dt><dd>${analysisState}</dd></div>
        </dl>
        <div class="mobile-ad-links">${externalLink(ad.ad_url, "الإعلان")} ${media}</div>
      </article>
    `;
  }).join("");
  document.getElementById("empty-state").hidden = ads.length !== 0;
  document.querySelectorAll("#ads-table-body tr, .mobile-ad-card").forEach((row) => row.addEventListener("click", () => openDetails(state.data.ads[Number(row.dataset.index)])));
}
function openDetails(ad) {
  const links = [externalLink(ad.ad_url, "فتح الإعلان"), externalLink(ad.video_url, "فتح الفيديو"), externalLink(ad.image_url, "فتح الصورة")].filter((link) => link !== "—").join(" ");
  const caption = text(ad.ad_body || "");
  const analysis = videoAnalysisBlock(ad);
  document.getElementById("dialog-content").innerHTML = `
    <p class="eyebrow">${text(ad.page_name)} · ${text(ad.ad_id)}</p>
    <h2>${text(ad.ad_title) || "إعلان"}</h2>
    <div class="dialog-body-wrap"><p class="dialog-body">${caption === "—" ? "—" : caption.replace(/\n/g, "<br>")}</p></div>
    <dl class="detail-list">
      <div><dt>تاريخ الإعلان</dt><dd>${text(ad.start_date)}</dd></div>
      <div><dt>المنصات</dt><dd>${platforms(ad).join(" · ") || "—"}</dd></div>
      <div><dt>CTA</dt><dd>${text(ad.cta)}</dd></div>
      <div><dt>النوع</dt><dd>${text(typeOf(ad))}</dd></div>
      <div><dt>رابط الإعلان</dt><dd>${externalLink(ad.ad_url, "فتح الإعلان")}</dd></div>
      <div><dt>الوسائط</dt><dd>${links || "لا توجد روابط وسائط"}</dd></div>
    </dl>
    ${analysis}
  `;
  document.getElementById("ad-dialog").showModal();
}
function renderCompetitors() {
  document.getElementById("competitors-grid").innerHTML = state.data.competitors.map((competitor) => `<article class="competitor-card"><div class="competitor-title"><h3>${text(competitor.name)}</h3><span>${text(competitor.total_ads)} إعلان</span></div><div class="competitor-stats"><span><b>${text(competitor.video_count)}</b> Video</span><span><b>${text(competitor.image_count)}</b> Image</span><span><b>${text(competitor.carousel_count)}</b> Carousel</span></div></article>`).join("") || "<p class=\"muted\">لا يوجد ملخص متاح.</p>";
}
async function init() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error("تعذر تحميل البيانات");
    state.data = await response.json();
    setText("total-ads", state.data.total_ads);
    setText("video-ads", state.data.total_video_ads ?? 0);
    setText("analyzed-video", state.data.analyzed_video_ads ?? 0);
    setText("competitor-count", state.data.competitors.length);
    setText("scan-date", state.data.scan_date);
    populateFilters();
    renderAds();
    renderCompetitors();
    ["competitor", "type", "platform"].forEach((name) => document.getElementById(`${name}-filter`).addEventListener("change", (event) => { state.filters[name] = event.target.value; renderAds(); }));
  } catch (error) {
    document.getElementById("empty-state").hidden = false;
    document.getElementById("empty-state").textContent = "تعذر تحميل latest.json. شغّل الفحص أولًا.";
  }
  document.getElementById("close-dialog").addEventListener("click", () => document.getElementById("ad-dialog").close());
  document.getElementById("ad-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
}

window.addEventListener("firebase-auth-ready", init, { once: true });
