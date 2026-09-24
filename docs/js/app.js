const state = { data: { ads: [], competitors: [] }, filters: { competitor: "", status: "", type: "", platform: "" } };

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
const isNew = (ad) => normalize(ad.comparison_result).includes("جديد") || normalize(ad.comparison_result).includes("new");

function setText(id, value) { document.getElementById(id).textContent = text(value); }
function externalLink(url, label) {
  if (!url || !/^https?:\/\//i.test(url)) return "—";
  return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}
function filteredAds() {
  return state.data.ads.filter((ad) => {
    const matchesCompetitor = !state.filters.competitor || ad.page_name === state.filters.competitor;
    const matchesStatus = !state.filters.status || (state.filters.status === "new" ? isNew(ad) : !isNew(ad));
    const matchesType = !state.filters.type || typeOf(ad) === state.filters.type;
    const matchesPlatform = !state.filters.platform || platforms(ad).includes(state.filters.platform);
    return matchesCompetitor && matchesStatus && matchesType && matchesPlatform;
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
  body.innerHTML = ads.map((ad, index) => {
    const media = ad.video_url ? externalLink(ad.video_url, "فيديو") : externalLink(ad.image_url, "صورة");
    return `<tr tabindex="0" data-index="${state.data.ads.indexOf(ad)}"><td><strong>${text(ad.page_name)}</strong></td><td class="mono">${text(ad.ad_id)}</td><td>${text(ad.start_date)}</td><td><span class="status-pill ${isNew(ad) ? "new" : "existing"}">${isNew(ad) ? "جديد" : "موجود"}</span></td><td>${text(typeOf(ad))}</td><td>${platforms(ad).join(" · ") || "—"}</td><td>${text(ad.cta)}</td><td>${text(ad.comparison_result)}</td><td class="link-stack">${externalLink(ad.ad_url, "الإعلان")} ${media}</td></tr>`;
  }).join("");
  document.getElementById("empty-state").hidden = ads.length !== 0;
  body.querySelectorAll("tr").forEach((row) => row.addEventListener("click", () => openDetails(state.data.ads[Number(row.dataset.index)])));
}
function openDetails(ad) {
  const links = [externalLink(ad.ad_url, "فتح الإعلان"), externalLink(ad.video_url, "فتح الفيديو"), externalLink(ad.image_url, "فتح الصورة")].filter((link) => link !== "—").join(" ");
  document.getElementById("dialog-content").innerHTML = `<p class="eyebrow">${text(ad.page_name)} · ${text(ad.ad_id)}</p><h2>${text(ad.ad_title)}</h2><p class="dialog-body">${text(ad.ad_body).replace(/\n/g, "<br>")}</p><dl class="detail-list"><div><dt>بداية الإعلان</dt><dd>${text(ad.start_date)}</dd></div><div><dt>المنصات</dt><dd>${platforms(ad).join(" · ") || "—"}</dd></div><div><dt>CTA</dt><dd>${text(ad.cta)}</dd></div><div><dt>المقارنة</dt><dd>${text(ad.comparison_result)}</dd></div><div><dt>الظهور</dt><dd>${text(ad.times_seen)} مرة</dd></div></dl><div class="dialog-links">${links || "لا توجد روابط وسائط"}</div>`;
  document.getElementById("ad-dialog").showModal();
}
function renderCompetitors() {
  document.getElementById("competitors-grid").innerHTML = state.data.competitors.map((competitor) => `<article class="competitor-card"><div class="competitor-title"><h3>${text(competitor.name)}</h3><span>${text(competitor.total_ads)} إعلان</span></div><div class="competitor-stats"><span><b>${text(competitor.total_new_ads)}</b> جديد</span><span><b>${text(competitor.video_count)}</b> Video</span><span><b>${text(competitor.image_count)}</b> Image</span><span><b>${text(competitor.carousel_count)}</b> Carousel</span></div></article>`).join("") || "<p class=\"muted\">لا يوجد ملخص متاح.</p>";
}
async function init() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error("تعذر تحميل البيانات");
    state.data = await response.json();
    setText("total-ads", state.data.total_ads);
    setText("new-ads", state.data.total_new_ads);
    setText("competitor-count", state.data.competitors.length);
    setText("last-scan", state.data.scan_date);
    setText("scan-date", state.data.scan_date);
    populateFilters();
    renderAds();
    renderCompetitors();
    ["competitor", "status", "type", "platform"].forEach((name) => document.getElementById(`${name}-filter`).addEventListener("change", (event) => { state.filters[name] = event.target.value; renderAds(); }));
  } catch (error) {
    document.getElementById("empty-state").hidden = false;
    document.getElementById("empty-state").textContent = "تعذر تحميل latest.json. شغّل الفحص أولًا.";
  }
  document.getElementById("close-dialog").addEventListener("click", () => document.getElementById("ad-dialog").close());
  document.getElementById("ad-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
}

window.addEventListener("firebase-auth-ready", init, { once: true });
