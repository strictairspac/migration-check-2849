import {store} from '/workspace/frontend/src/stores/business.js';
import {drillsPage,drillsUi} from '/workspace/frontend/src/pages/drills.js';
let fails=0;
const ok=(n,c)=>{console.log((c?'PASS ':'FAIL ')+n);if(!c)fails++;};
store.user={role:'operator',email:'op'};
store.runs=[
 {id:1,name:'运行A',status:'completed',created_at:'2026-11-17',result:{accepted_count:12}},
 {id:2,name:'运行B',status:'completed',created_at:'2026-11-17',result:{accepted_count:2}},
 {id:3,name:'运行C',status:'running',created_at:'2026-11-18',progress:null},
];
store.drillPackages=[
 {id:7,name:'qc-华东',recipient_group:'华东复核组',status:'open',version:2,row_count:14,run_ids:[1],job:{id:9,status:'completed',run_ids:[2],processed:[2],target_version:2,error:null}},
 {id:8,name:'qc-华南',recipient_group:'华南复核组',status:'withdrawn',version:1,row_count:12,run_ids:[1],job:{id:11,status:'aborted',run_ids:[2],processed:[],target_version:2,error:'演练包已撤回，追加中止'}},
 {id:9,name:'qc-华北',recipient_group:'华北复核组',status:'open',version:0,row_count:0,run_ids:[],job:{id:12,status:'failed',run_ids:[1],processed:[],target_version:1,error:'模拟崩溃'}},
];
store.drillDetail={7:{versions:[{version:1,row_count:12,checksum:'ab'.repeat(32),added_run_ids:[1]},{version:2,row_count:14,checksum:'cd'.repeat(32),added_run_ids:[2]}],jobs:[{id:9,status:'completed',run_ids:[2],processed:[2],target_version:2,error:null}],aliases:[{sample_code:'JS-001',alias:'D-AAAAAA-0001'}],run_ids:[1,2]}};
let html=drillsPage();
ok('操作员视图渲染',html.includes('qc-华东')&&html.includes('华东复核组'));
ok('开放包显示下载/追加/撤回',html.includes('data-drill-download="7"')&&html.includes('data-drill-append="7"')&&html.includes('data-drill-withdraw="7"'));
ok('撤回包显示重开不显示下载',!html.includes('data-drill-download="8"')&&html.includes('data-drill-reopen="8"'));
ok('失败任务显示续跑',html.includes('data-drill-resume="12"'));
ok('运行中运行不出现在选择器',!html.includes('value="3"'));
ok('版本0包无下载按钮',!html.includes('data-drill-download="9"'));
drillsUi.toggleAppend(7);
html=drillsPage();
const panel=html.split('id="append-form"')[1]||'';
ok('追加面板展开且排除已收录运行',panel.includes('value="2"')&&!panel.includes('value="1"'));
drillsUi.toggleAppend(7);drillsUi.toggleDetail(7);
html=drillsPage();
ok('详情面板显示版本与对照表',html.includes('v1')&&html.includes('JS-001')&&html.includes('D-AAAAAA-0001'));
drillsUi.toggleDetail(7);
store.user={role:'viewer',email:'vw'};
html=drillsPage();
ok('观察员只见下载不见变更按钮',html.includes('data-drill-download="7"')&&!html.includes('data-drill-append')&&!html.includes('data-drill-withdraw')&&!html.includes('data-drill-reopen')&&!html.includes('data-drill-resume'));
store.drillPackages=[];
html=drillsPage();
ok('空态渲染',html.includes('还没有演练包'));
console.log(fails?`\n${fails} 项失败`:'\n前端冒烟全部通过');
process.exit(fails?1:0);
