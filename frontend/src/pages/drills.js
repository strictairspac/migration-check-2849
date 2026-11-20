import {store} from '../stores/business.js';import {esc,json} from '../utils/html.js';import {table} from '../components/common/table.js';import {status} from '../components/common/status.js';import {DSTATUSES} from '../constants/enums.js';
let appendFor=null,detailFor=null;
export const drillsUi={toggleAppend:id=>{appendFor=appendFor===id?null:id;detailFor=null;},toggleDetail:id=>{detailFor=detailFor===id?null:id;appendFor=null;}};
const picker=runs=>runs.length?runs.map(r=>`<label class="check"><input type="checkbox" name="run_ids" value="${r.id}"><span>#${r.id} ${esc(r.name)} <small>${r.result?r.result.accepted_count+'行已交接':''}</small></span></label>`).join(''):'<p class="muted">暂无可选择的已完成运行。</p>';
const dstat=s=>`<span class="status ${s}">${DSTATUSES[s]||s}</span>`;
function actions(p){
 const mine=store.user.role!=='viewer',j=p.job,active=j&&['queued','running'].includes(j.status),parts=[];
 if(p.status==='open'&&p.version>=1)parts.push(`<button class="quiet" data-drill-download="${p.id}">下载副本 v${p.version} ↓</button>`);
 if(mine&&p.status==='open')parts.push(`<button class="quiet" data-drill-append="${p.id}" ${active?'disabled':''}>追加运行</button>`);
 if(mine&&j&&['running','failed'].includes(j.status))parts.push(`<button class="quiet" data-drill-resume="${j.id}">续跑</button>`);
 if(mine&&p.status==='open')parts.push(`<button class="quiet" data-drill-withdraw="${p.id}">撤回</button>`);
 if(mine&&p.status==='withdrawn')parts.push(`<button class="quiet" data-drill-reopen="${p.id}">重开（换代号）</button>`);
 parts.push(`<button class="quiet" data-drill-detail="${p.id}">详情</button>`);
 return parts.join('');
}
function panel(p){
 if(appendFor===p.id){
  const fresh=store.runs.filter(r=>r.status==='completed'&&!p.run_ids.includes(r.id));
  return `<tr class="panel"><td colspan="5"><form id="append-form" data-package="${p.id}"><h3>追加已完成运行 → ${esc(p.name)}</h3><p>追加不改旧代号与已发版本；新行进入下一版，完成前下载仍取 v${p.version}。</p>${picker(fresh)}<button type="submit" ${fresh.length?'':'disabled'}>提交追加任务 →</button></form></td></tr>`;
 }
 if(detailFor===p.id){
  const d=store.drillDetail[p.id];
  if(!d)return `<tr class="panel"><td colspan="5"><p class="muted">正在读取详情…</p></td></tr>`;
  return `<tr class="panel"><td colspan="5"><h3>版本凭据</h3>${table(['版本','行数','摘要','收录运行'],d.versions.map(v=>[`v${v.version}`,v.row_count,`<code class="checksum">${esc(v.checksum.slice(0,16))}…</code>`,(v.added_run_ids||[]).map(i=>'#'+i).join(' ')]))}<h3>追加任务</h3>${table(['任务','状态','进度','目标版本'],d.jobs.map(j=>['#'+j.id,status(j.status),`${(j.processed||[]).length}/${(j.run_ids||[]).length}个运行${j.error?' · '+esc(j.error):''}`,'v'+j.target_version]))}<h3>代号对照 · 仅站内留存，下载包不含</h3>${table(['原委托号','代号'],d.aliases.map(a=>[`<code>${esc(a.sample_code)}</code>`,`<code>${esc(a.alias)}</code>`]))}</td></tr>`;
 }
 return '';
}
export function drillsPage(){
 const completed=store.runs.filter(r=>r.status==='completed');
 const rows=[];
 for(const p of store.drillPackages){
  const j=p.job,jobInfo=j?status(j.status)+`<small>任务#${j.id} · ${(j.processed||[]).length}/${(j.run_ids||[]).length}个运行</small>`:'<small class="muted">—</small>';
  rows.push([`<b>${esc(p.name)}</b><small>接收组：${esc(p.recipient_group)}</small>`,dstat(p.status),`v${p.version}<small>${p.row_count}行脱敏结果</small>`,jobInfo,actions(p)].map(c=>`<td>${c}</td>`).join(''));
 }
 const body=store.drillPackages.map((p,i)=>`<tr>${rows[i]}</tr>${panel(p)}`).join('');
 const listing=store.drillPackages.length?`<div class=table-wrap><table><thead><tr><th>演练包 / 接收组</th><th>状态</th><th>已发版本</th><th>最近任务</th><th>操作</th></tr></thead><tbody>${body}</tbody></table></div>`:'<div class=empty>还没有演练包。选择左侧已完成运行，为接收组生成第一份脱敏副本。</div>';
 return `<div class="split"><section><h2>为质检演练签发脱敏副本</h2><p>从已完成的迁移运行生成可下载副本：委托号替换为代号，对照表只留站内，下载包不含原委托号。同一接收组内同一委托跨运行同代号；撤回后旧版即不可再取，重开必换代号。</p><form id="drill-form"><label>演练包名称<input name="name" placeholder="qc-drill-2026-华东" required></label><label>接收组<input name="recipient_group" placeholder="华东复核组" required></label><h3>选择已完成运行 <em>${completed.length}</em></h3>${picker(completed)}<button type="submit">创建演练包${completed.length?'并入队首批追加':''} →</button></form><ol class="steps"><li>冻结所选运行的目标行为脱敏行</li><li>同一委托分配稳定代号，组间互不相同</li><li>后台逐运行追加，中断可续跑、重试不重复</li><li>完成即发新版；完成前下载仍取上一版</li></ol></section><section><h2>演练包 <em>${store.drillPackages.length}</em></h2>${listing}<aside class="note">撤回与追加可并发进行：撤回立即生效，进行中的追加会安全中止。重开为同一接收组创建全新代号空间的新包。</aside></section></div>`;
}
