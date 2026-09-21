/* People Intelligence engine - pure functions, no DOM. Runs in the browser and in node (for tests). */
(function (root) {
  const MS = 86400000;
  const dn = (y, m, d) => Math.round(Date.UTC(y, m - 1, d) / MS);           // y, m(1-12), d -> day number
  const fromISO = s => { const [y, m, d] = s.split("-").map(Number); return dn(y, m, d); };
  const toDate = n => new Date(n * MS);
  const iso = n => toDate(n).toISOString().slice(0, 10);
  const monthStart = n => { const t = toDate(n); return dn(t.getUTCFullYear(), t.getUTCMonth() + 1, 1); };
  const addMonths = (n, k) => { const t = toDate(n); return dn(t.getUTCFullYear(), t.getUTCMonth() + 1 + k, 1); };
  const qLabel = n => { const t = toDate(n); return "Q" + (Math.floor(t.getUTCMonth() / 3) + 1) + " " + t.getUTCFullYear(); };
  const qKey = n => { const t = toDate(n); return t.getUTCFullYear() * 10 + Math.floor(t.getUTCMonth() / 3); };
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
  const sum = a => a.reduce((x, y) => x + y, 0);

  function Engine(payload) {
    const P = payload, meta = P.meta;
    const emps = P.emps.map(r => { const o = {}; P.ecols.forEach((c, i) => o[c] = r[i]); return o; });
    const byId = new Map(); emps.forEach(e => { if (!byId.has(e.id) || (e.term == null)) byId.set(e.id, e); });   // latest spell wins
    const kids = new Map(); const seenKid = new Set();
    emps.forEach(e => { if (e.mgr != null && !seenKid.has(e.id)) { seenKid.add(e.id); if (!kids.has(e.mgr)) kids.set(e.mgr, []); kids.get(e.mgr).push(e.id); } });
    const byIdAll = new Map(); emps.forEach(e => { if (!byIdAll.has(e.id)) byIdAll.set(e.id, []); byIdAll.get(e.id).push(e); });
    const reasons = meta.reasons;
    const ASOF = fromISO(meta.asof);
    const FIRST = fromISO(meta.first_full_month);

    // comp index: id -> {B:[[date,usd]...], T:[...]} sorted
    const comp = new Map();
    P.comp.forEach(([id, c, d, u]) => { if (!comp.has(id)) comp.set(id, { B: [], T: [] }); comp.get(id)[c].push([d, u]); });
    comp.forEach(v => { v.B.sort((a, b) => a[0] - b[0]); v.T.sort((a, b) => a[0] - b[0]); });
    const latest = (arr, d) => { let r = null; for (const x of arr) { if (x[0] <= d) r = x[1]; else break; } return r; };

    // leaders = anyone with >=1 report
    const leaders = [...kids.keys()].map(id => byId.get(id)).filter(Boolean)
      .sort((a, b) => meta.levels.indexOf(a.level) - meta.levels.indexOf(b.level) || a.name.localeCompare(b.name));
    const ceo = emps.find(e => e.mgr == null);

    function orgIds(leaderId, includeLeader) {
      const out = new Set(); if (leaderId == null) { emps.forEach(e => out.add(e.id)); return out; }
      const st = [leaderId]; const seen = new Set([leaderId]);
      while (st.length) { const x = st.pop(); for (const k of (kids.get(x) || [])) if (!seen.has(k)) { seen.add(k); out.add(k); st.push(k); } }
      if (includeLeader) out.add(leaderId); return out;
    }
    function select({ leader = null, includeLeader = true, wt = "F" } = {}) {
      const ids = orgIds(leader, includeLeader);
      return emps.filter(e => ids.has(e.id) && (wt === "A" || e.wt === wt));
    }
    const activeAt = (e, d) => e.hire <= d && (e.term == null || e.term > d);
    const hcAt = (L, d) => { let n = 0; for (const e of L) if (activeAt(e, d)) n++; return n; };
    const lt1At = (L, d) => { let n = 0; for (const e of L) if (activeAt(e, d) && (d - e.hire) < 365) n++; return n; };

    function monthly(L, asof = ASOF) {
      const out = []; const endMonth = monthStart(asof - 1);           // last month with a full set of data
      for (let ms = FIRST; ms <= endMonth; ms = addMonths(ms, 1)) {
        const me = addMonths(ms, 1) - 1, prev = ms - 1;
        const m = { ms, me, label: iso(ms).slice(0, 7), start: hcAt(L, prev), end: hcAt(L, me), lt1Start: lt1At(L, prev), lt1End: lt1At(L, me),
          hires: 0, exits: 0, vol: 0, invol: 0, volLt1: 0, volGe1: 0, invLt1: 0, invGe1: 0 };
        for (const e of L) {
          if (e.hire >= ms && e.hire <= me) m.hires++;
          if (e.term != null && e.term >= ms && e.term <= me) {
            m.exits++; const early = (e.term - e.hire) < 365;
            if (e.tt === "V") { m.vol++; early ? m.volLt1++ : m.volGe1++; } else { m.invol++; early ? m.invLt1++ : m.invGe1++; }
          }
        }
        m.avg = (m.start + m.end) / 2; m.avgLt1 = (m.lt1Start + m.lt1End) / 2; m.avgGe1 = m.avg - m.avgLt1;
        out.push(m);
      }
      return out;
    }
    const rate = (n, pop, months) => pop > 0 ? (n / pop) * (12 / months) : null;

    function quarterly(M) {
      const g = new Map();
      M.forEach(m => { const k = qKey(m.ms); if (!g.has(k)) g.set(k, []); g.get(k).push(m); });
      return [...g.entries()].sort((a, b) => a[0] - b[0]).map(([k, ms]) => {
        const n = ms.length, first = ms[0];
        const o = { key: k, label: qLabel(first.ms), months: n, partial: n < 3 || first.ms !== monthStart(first.ms) || (toDate(first.ms).getUTCMonth() % 3 !== 0),
          hires: sum(ms.map(m => m.hires)), exits: sum(ms.map(m => m.exits)), vol: sum(ms.map(m => m.vol)), invol: sum(ms.map(m => m.invol)),
          volLt1: sum(ms.map(m => m.volLt1)), volGe1: sum(ms.map(m => m.volGe1)),
          avg: mean(ms.map(m => m.avg)), avgLt1: mean(ms.map(m => m.avgLt1)), avgGe1: mean(ms.map(m => m.avgGe1)), endHc: ms[n - 1].end };
        o.volRate = rate(o.vol, o.avg, n); o.totRate = rate(o.exits, o.avg, n);
        o.lt1Rate = rate(o.volLt1, o.avgLt1, n); o.ge1Rate = rate(o.volGe1, o.avgGe1, n);
        return o;
      });
    }
    function rolling12(M) {
      const out = [];
      for (let i = 11; i < M.length; i++) {
        const w = M.slice(i - 11, i + 1);
        out.push({ label: M[i].label, vol: sum(w.map(m => m.vol)), volRate: rate(sum(w.map(m => m.vol)), mean(w.map(m => m.avg)), 12),
          lt1Rate: rate(sum(w.map(m => m.volLt1)), mean(w.map(m => m.avgLt1)), 12), ge1Rate: rate(sum(w.map(m => m.volGe1)), mean(w.map(m => m.avgGe1)), 12),
          volLt1: sum(w.map(m => m.volLt1)), avgLt1: mean(w.map(m => m.avgLt1)) });
      }
      return out;
    }
    function ttmSummary(L, asof = ASOF) { const r = rolling12(monthly(L, asof)); return r.length ? r[r.length - 1] : null; }

    function tccOf(L, asof = ASOF) {
      let base = 0, bonus = 0, n = 0, missing = 0; const rows = [];
      for (const e of L) {
        if (!activeAt(e, asof)) continue; n++;
        const c = comp.get(e.id); const b = c ? latest(c.B, asof) : null, t = c ? latest(c.T, asof) : null;
        if (b == null) missing++; base += b || 0; bonus += t || 0; rows.push({ e, b: b || 0, t: t || 0 });
      }
      return { n, base, bonus, tcc: base + bonus, missing, rows };
    }
    function breakdown(L, key, asof = ASOF) {
      const t = tccOf(L, asof); const g = new Map();
      t.rows.forEach(r => { const k = r.e[key]; if (!g.has(k)) g.set(k, { key: k, n: 0, tcc: 0, base: 0, bonus: 0 }); const o = g.get(k); o.n++; o.tcc += r.b + r.t; o.base += r.b; o.bonus += r.t; });
      return [...g.values()];
    }
    function cohorts(L, asof = ASOF) {
      const wins = [90, 180, 365]; const g = new Map();
      for (const e of L) {
        if (e.hire < fromISO(meta.term_log_start) || e.hire > asof) continue;      // earlier hires are survivor-biased (leavers before the log started are missing)
        const k = qKey(e.hire); if (!g.has(k)) g.set(k, { key: k, label: qLabel(e.hire), hires: 0, w: { 90: [0, 0], 180: [0, 0], 365: [0, 0] } });
        const o = g.get(k); o.hires++;
        wins.forEach(w => { if (asof - e.hire >= w) { o.w[w][0]++; if (e.tt === "V" && e.term != null && (e.term - e.hire) < w) o.w[w][1]++; } });
      }
      return [...g.values()].sort((a, b) => a.key - b.key);
    }
    function exitReasons(L, from, to, earlyOnly) {
      const g = new Map();
      for (const e of L) if (e.tt === "V" && e.term != null && e.term >= from && e.term <= to && (!earlyOnly || (e.term - e.hire) < 365)) {
        const r = reasons[e.reason]; g.set(r, (g.get(r) || 0) + 1);
      }
      return [...g.entries()].map(([k, v]) => ({ reason: k, n: v })).sort((a, b) => b.n - a.n);
    }
    function pendingComp(asof = ASOF, L = null) {
      const ids = L ? new Set(L.filter(x => activeAt(x, asof)).map(x => x.id)) : null; let n = 0, usd = 0, first = null; const seen = new Set();
      comp.forEach((v, id) => { if (ids && !ids.has(id)) return; ["B","T"].forEach(k => { const cur = latest(v[k], asof); const fut = v[k].filter(x => x[0] > asof);
        if (fut.length) { const nx = fut[0]; usd += nx[1] - (cur || 0); if (!seen.has(id)) { seen.add(id); n++; } if (first == null || nx[0] < first) first = nx[0]; } }); });
      return { n, usd, date: first == null ? "" : iso(first) };
    }
    function children(leaderId) { return (kids.get(leaderId) || []).map(id => byId.get(id)).filter(Boolean); }
    function chain(id) { const out = []; let e = byId.get(id); while (e) { out.unshift(e); e = e.mgr != null ? byId.get(e.mgr) : null; } return out; }
    function subOrgRows(leaderId, wt = "F", asof = ASOF) {
      return children(leaderId).filter(c => (kids.get(c.id) || []).length).map(c => {
        const L = select({ leader: c.id, includeLeader: true, wt }); const t = tccOf(L, asof); const r = ttmSummary(L, asof);
        return { e: c, n: t.n, tcc: t.tcc, vol: r ? r.volRate : null, lt1: r ? r.lt1Rate : null, lt1n: r ? r.volLt1 : 0, lt1pop: r ? r.avgLt1 : 0 };
      }).sort((a, b) => b.n - a.n);
    }
    return { P, meta, emps, byId, leaders, ceo, ASOF, FIRST, select, orgIds, activeAt, hcAt, lt1At, monthly, quarterly, rolling12, ttmSummary, tccOf, breakdown, cohorts, exitReasons, pendingComp, children, chain, subOrgRows, kids, iso, fromISO, qLabel, dn, toDate, addMonths, monthStart };
  }
  root.PIEngine = Engine;
  if (typeof module !== "undefined") module.exports = Engine;
})(typeof window !== "undefined" ? window : globalThis);
