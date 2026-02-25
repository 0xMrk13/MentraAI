(function(){
  const root = document.getElementById("hmData");
  if (!root) return;

  let labels = [];
  let values = [];
  try{
    labels = JSON.parse(root.dataset.labels || "[]");
    values = JSON.parse(root.dataset.values || "[]");
  }catch(e){
    labels = [];
    values = [];
  }

  const map = new Map();
  for(let i=0; i<labels.length; i++){
    map.set(String(labels[i]), Number(values[i] || 0));
  }

  const params = new URLSearchParams(window.location.search);
  const now = new Date();
  const currentYear = now.getFullYear();
  const year = Number(params.get("year") || currentYear);

  const yearLabel = document.getElementById("hmYearLabel");
  const prevBtn = document.getElementById("hmPrevYear");
  const nextBtn = document.getElementById("hmNextYear");
  const totalEl = document.getElementById("hmTotalYear");

  const wrap = document.getElementById("hmWrap");
  const noData = document.getElementById("hmNoData");
  const grid = document.getElementById("hmGrid");
  const monthsEl = document.getElementById("hmMonths");

  if (!yearLabel || !prevBtn || !nextBtn || !totalEl || !wrap || !noData || !grid || !monthsEl) return;

  function setYearLink(el, y){
    const u = new URL(window.location.href);
    u.searchParams.set("year", String(y));
    el.href = u.pathname + "?" + u.searchParams.toString();
  }

  yearLabel.textContent = String(year);
  setYearLink(prevBtn, year - 1);
  setYearLink(nextBtn, year + 1);

  function ymd(d){
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const dd = String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${dd}`;
  }
  function addDays(date, n){
    const d = new Date(date);
    d.setDate(d.getDate() + n);
    return d;
  }

  const start = new Date(year, 0, 1);
  const end   = new Date(year, 11, 31);

  const startAligned = addDays(start, -start.getDay());       // back to Sunday
  const endAligned   = addDays(end, (6 - end.getDay()));      // forward to Saturday

  let totalYear = 0;
  for(const [d, v] of map.entries()){
    if(d.startsWith(String(year) + "-")) totalYear += (Number(v) || 0);
  }
  totalEl.textContent = String(totalYear);

  noData.classList.toggle("d-none", totalYear !== 0);
  wrap.classList.remove("d-none");

  let maxV = 0;
  for(const [d, v] of map.entries()){
    if(d.startsWith(String(year) + "-")) maxV = Math.max(maxV, Number(v)||0);
  }
  if(maxV <= 0) maxV = 1;

  function level(v){
    v = Number(v)||0;
    if(v <= 0) return 0;
    const r = v / maxV;
    if(r <= 0.25) return 1;
    if(r <= 0.50) return 2;
    if(r <= 0.75) return 3;
    return 4;
  }

  const daysCount = Math.round((endAligned - startAligned) / (1000*60*60*24)) + 1;
  const weeks = Math.ceil(daysCount / 7);

  const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const cell = 12, gap = 4;
  const colW = cell + gap;

  monthsEl.innerHTML = "";
  monthsEl.style.width = "max-content";

  for(let m=0; m<12; m++){
    const md = new Date(year, m, 1);
    const mdAligned = addDays(md, -md.getDay());
    const weekIdx = Math.round((mdAligned - startAligned) / (1000*60*60*24*7));
    if(weekIdx >= 0 && weekIdx < weeks){
      const lab = document.createElement("div");
      lab.className = "m";
      lab.textContent = monthNames[m];
      lab.style.left = (weekIdx * colW) + "px";
      monthsEl.appendChild(lab);
    }
  }

  const frag = document.createDocumentFragment();
  let d = new Date(startAligned);

  for(let i=0; i<daysCount; i++){
    const dateStr = ymd(d);
    const inYear = d >= start && d <= end;

    const v = inYear ? (map.get(dateStr) || 0) : 0;
    const lv = inYear ? level(v) : 0;

    const div = document.createElement("div");
    div.className = `hm-cell lv${lv}` + (inYear ? "" : " hm-muted");

    if(inYear){
      div.title = `${v} point${v===1?"":"s"} on ${dateStr}`;
      div.setAttribute("aria-label", div.title);
    } else {
      div.setAttribute("aria-hidden", "true");
    }

    frag.appendChild(div);
    d = addDays(d, 1);
  }

  grid.innerHTML = "";
  grid.appendChild(frag);
})();
