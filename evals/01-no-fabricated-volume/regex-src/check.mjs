// Checks graders/no-volume-figure-patterns.md.
// Usage (from the case directory): node regex-src/check.mjs graders/no-volume-figure-patterns.md [dir to scan ...]
// 1. reads the grader file the way the eval runner does (frontmatter split, body.trim(), new RegExp(body, flags))
// 2. confirms the body is exactly what build.mjs generates
// 3. runs the corpus: every `bad` line must match, no `good` line may match
// 4. scans text files under the given directories (default: ../../skills/seo-operator if it exists) and prints hits
// 5. times the pattern on long whitespace runs and long tables (catastrophic backtracking guard)
import fs from 'fs';
import path from 'path';
import { pattern } from './build.mjs';
import { bad, good, llmOnly } from './corpus.mjs';

const file = process.argv[2] || 'graders/no-volume-figure-patterns.md';
const txt = fs.readFileSync(file, 'utf8');
const m = txt.match(/^---\s*\n([\s\S]*?)---\s*\n?/);
if (!m) throw new Error('no frontmatter');
const body = txt.slice(m[0].length).trim();
const flagsLine = m[1].split('\n').find((l) => /^flags:/.test(l));
const flags = flagsLine ? flagsLine.replace(/^flags:\s*/, '').trim() : '';
const re = new RegExp(body, flags);
let problems = 0;
if (body !== pattern) { problems++; console.log('DIFFERS from build.mjs output: regenerate with `node regex-src/build.mjs write', file + '`'); }
for (const s of bad) if (!re.test(s)) { problems++; console.log('MISS  ', JSON.stringify(s)); }
for (const s of good) { const h = s.match(re); if (h) { problems++; console.log('FALSE+', JSON.stringify(s), '=>', JSON.stringify(h[0])); } }
const llmHits = llmOnly.filter((s) => re.test(s)).length;
console.log(`corpus: bad ${bad.length}, good ${good.length}, llmOnly ${llmOnly.length} (regex hits ${llmHits}, informational)`);

const dirs = process.argv.slice(3);
const def = path.resolve(path.dirname(file), '..', '..', '..', 'skills', 'seo-operator');
if (dirs.length === 0 && fs.existsSync(def)) dirs.push(def);
const g = new RegExp(body, flags.includes('g') ? flags : flags + 'g');
const walk = (d) => {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f);
    if (fs.statSync(p).isDirectory()) { walk(p); continue; }
    if (!/\.(md|txt|py|csv|json|ya?ml)$/.test(f)) continue;
    const t = fs.readFileSync(p, 'utf8');
    for (const h of t.matchAll(g)) {
      const ln = t.slice(0, h.index).split('\n').length;
      const line = t.split('\n')[ln - 1];
      const note = line.includes('違反例') ? ' (expected: a 違反例 line is itself a fabricated figure)' : '';
      console.log(`scan hit${note} ${p}:${ln} ${JSON.stringify(h[0])} | ${line.slice(0, 100)}`);
    }
  }
};
for (const d of dirs) { console.log('scanning', d); walk(d); }

const cases = [];
for (const n of [100, 1000, 5000]) {
  const sp = ' '.repeat(n), fw = '　'.repeat(n);
  cases.push([`月間+${n}sp`, '月間' + sp + 'x'], [`約+${n}sp`, '約' + sp + 'x'], [`キーケース|${n}sp`, '| キーケース 本革 |' + sp + 'x'],
    [`cell ${n}sp`, '| 検索ボリューム |\n|' + sp + '|' + sp + '|\n| 本革 |' + sp + '12' + sp + 'x'], [`キーケース ${n}fw`, 'キーケース' + fw + '：' + fw + 'x'],
    [`数字列 ${n}`, '1'.repeat(n) + 'x'], [`カンマ列 ${n}`, '1,000'.repeat(n / 10) + 'x']);
}
let table = '| キーワード | 月間検索ボリューム | 検索意図 | CVへの近さ | 影響度 | 工数 | 優先度 |\n|---|---|---|---|---|---|---|\n';
for (let i = 0; i < 300; i++) table += `| キーケース 本革（${'候補'.repeat(i % 7)}） | [要追加: 検索ボリューム] | 比較検討 | 4 | 3 | 2 | 1.5 |\n`;
cases.push(['table 300 rows', table], ['answer x50', (good.join('\n') + '\n').repeat(50)]);
let worst = 0;
for (const [label, s] of cases) {
  const t0 = process.hrtime.bigint(); const hit = re.test(s); const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  worst = Math.max(worst, ms);
  if (ms > 200 || (hit && !label.startsWith('cell'))) { problems++; console.log('SLOW/HIT', label, ms.toFixed(1) + 'ms', hit); }
}
console.log(`timing: worst ${worst.toFixed(1)}ms over ${cases.length} inputs`);
console.log(problems ? `PROBLEMS ${problems}` : 'OK', `pattern length ${body.length}`);
process.exitCode = problems ? 1 : 0;
