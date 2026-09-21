const Engine=require('../engine.js'); const P=require('../payload.json'); const ref=require('../reference_answers.json');
const E=Engine(P); const byName=n=>E.emps.find(e=>e.name===n).id;
let fail=0; const chk=(l,a,b,tol=1)=>{const ok=Math.abs(a-b)<=tol; if(!ok)fail++; console.log(ok?'PASS':'FAIL',l,a,b)};
const co=E.select({wt:'F'}); chk('company FTE',E.hcAt(co,E.ASOF),ref.company.fte); chk('company TCC',E.tccOf(co).tcc,ref.company.tcc);
for(const nm of ['Morgan Reyes','Dana Whitfield']) for(const inc of [true,false]){
  const L=E.select({leader:byName(nm),includeLeader:inc,wt:'F'}); const t=E.tccOf(L); const r=ref[`${nm}|${inc?'incl':'excl'}`];
  chk(nm+(inc?' incl':' excl')+' FTE',t.n,r.fte); chk(nm+' TCC',t.tcc,r.tcc); chk(nm+' base',t.base,r.base); chk(nm+' bonus',t.bonus,r.bonus);}
const q=E.quarterly(E.monthly(co)); console.log(q.map(x=>[x.label,x.months,x.vol,(x.volRate*100).toFixed(1),(x.lt1Rate*100).toFixed(1),(x.ge1Rate*100).toFixed(1),x.partial].join(' | ')).join('\n'));
const m=E.monthly(co); console.log(m.slice(-9).map(x=>[x.label,x.end,x.hires,x.exits].join(' ')).join('\n'));
console.log(E.rolling12(m).map(x=>x.label+' '+(x.volRate*100).toFixed(1)+' lt1 '+(x.lt1Rate*100).toFixed(1)).join('\n'));
console.log(E.subOrgRows(E.ceo.id).map(r=>[r.e.name,r.n,Math.round(r.tcc),(r.vol*100).toFixed(1),(r.lt1*100).toFixed(1),r.lt1n].join(' | ')).join('\n'));
console.log(fail?'FAILURES '+fail:'ALL PASS');
