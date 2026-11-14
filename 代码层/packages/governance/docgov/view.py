"""治理注册表视图：把索引渲染成可离线双击打开的 HTML。

由 index 命令在重建 state/index.json 后调用；只读索引数据，不修改任何资产。
"""
from __future__ import annotations

import json
from pathlib import Path


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>治理注册表视图</title>
<style>
:root{--bg:#0f1216;--card:#171c22;--line:#26303a;--fg:#e6edf3;--mut:#8b98a5;--acc:#4da3ff;--ok:#3fb950;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
header{padding:18px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{margin:0 0 6px;font-size:18px}
.meta{color:var(--mut);font-size:12px}
main{padding:18px 22px;max-width:1080px;margin:0 auto}
.tabs{display:flex;gap:8px;margin:14px 0}
.tabs button{background:var(--card);border:1px solid var(--line);color:var(--fg);padding:6px 12px;border-radius:8px;cursor:pointer}
.tabs button.on{border-color:var(--acc);color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.card h3{margin:0 0 4px;font-size:15px}
.uri{color:var(--mut);font-size:12px;word-break:break-all}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line);color:var(--mut);margin-left:6px}
.badge.active{color:var(--ok);border-color:var(--ok)}
.badge.planned{color:var(--warn);border-color:var(--warn)}
.sec{margin-top:10px}
.sec .lbl{color:var(--mut);font-size:12px;margin-bottom:4px}
.item{display:flex;gap:8px;align-items:baseline;padding:3px 0;border-top:1px dashed var(--line)}
.item:first-child{border-top:0}
.item a{color:var(--acc);text-decoration:none;word-break:break-all}
.item .t{color:var(--mut);font-size:12px;flex:none}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:500}
code{background:#0b0e11;border:1px solid var(--line);border-radius:6px;padding:1px 5px;font-size:12px;word-break:break-all}
.empty{color:var(--mut);font-size:12px}
</style>
</head>
<body>
<header>
  <h1 id="title">治理注册表视图</h1>
  <div class="meta" id="meta"></div>
  <div class="tabs">
    <button id="tab-modules" class="on">模块总览</button>
    <button id="tab-objects">全部对象</button>
    <button id="tab-links">关系</button>
  </div>
</header>
<main>
  <div id="view-modules" class="grid"></div>
  <div id="view-objects" style="display:none"></div>
  <div id="view-links" style="display:none"></div>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const byUri = {}; D.objects.forEach(o => byUri[o.uri] = o);
const outLinks = {}; const inLinks = {};
D.links.forEach(l => { (outLinks[l.source]=outLinks[l.source]||[]).push(l); (inLinks[l.target]=inLinks[l.target]||[]).push(l); });
const esc = s => (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const nm = u => { const o=byUri[u]; return o? o.name : u; };

document.getElementById('title').textContent = (D.project && D.project.name ? D.project.name : '项目') + ' · 治理注册表视图';
const counts = {}; D.objects.forEach(o=>counts[o.type]=(counts[o.type]||0)+1);
document.getElementById('meta').textContent =
  '对象 ' + D.objects.length + ' · 关系 ' + D.links.length + ' · ' +
  Object.entries(counts).map(([k,v])=>k+' '+v).join(' / ');

function linksFrom(uri, type){ return (outLinks[uri]||[]).filter(l=>l.type===type).map(l=>l.target); }
function linksTo(uri, type){ return (inLinks[uri]||[]).filter(l=>l.type===type).map(l=>l.source); }
function objList(uris, filterFn){ return uris.map(u=>byUri[u]).filter(Boolean).filter(o=>!filterFn||filterFn(o)); }

function bucket(label, items){
  if(!items.length) return '';
  return '<div class="sec"><div class="lbl">'+label+'</div>' + items.map(o=>
    '<div class="item"><span class="t">'+esc(o.kind||o.type||'')+'</span><span title="'+esc(o.uri)+'">'+esc(o.name)+'</span></div>'
  ).join('') + '</div>';
}

function moduleCard(m){
  const code = objList(linksTo(m.uri,'implements'), o=>o.type==='code');
  const curDocs = objList(linksTo(m.uri,'describes'), o=>o.type==='document' && o.kind!=='verification');
  const verif = objList(linksTo(m.uri,'verifies'), o=>o.type==='document');
  const decisions = objList(linksTo(m.uri,'affects'), o=>o.type==='decision');
  const acts = objList(linksTo(m.uri,'affects'), o=>o.type==='activity');
  const deps = linksFrom(m.uri,'depends_on');
  let h = '<div class="card"><h3>'+esc(m.name)+'<span class="badge '+esc(m.status)+'">'+esc(m.status)+'</span></h3>'+
    '<div class="uri">'+esc(m.uri)+'</div>';
  h += bucket('代码位置', code.map(o=>({name:o.name+'  ['+(o.location||'')+']', type:'code'})));
  h += bucket('现行文档', curDocs);
  h += bucket('验证', verif);
  h += bucket('决策', decisions);
  h += bucket('过程记录', acts);
  if(deps.length) h += bucket('依赖', deps.map(u=>({name:nm(u), type:''})));
  h += '</div>';
  return h;
}

const modules = D.objects.filter(o=>o.type==='module');
document.getElementById('view-modules').innerHTML = modules.length ? modules.map(moduleCard).join('') : '<div class="empty">暂无模块</div>';

const order = ['project','module','workflow','document','decision','activity','code'];
const rows = D.objects.slice().sort((a,b)=> (order.indexOf(a.type)-order.indexOf(b.type)) || a.uri.localeCompare(b.uri));
document.getElementById('view-objects').innerHTML = '<table><tr><th>类型</th><th>名称</th><th>URI</th><th>状态</th><th>位置</th></tr>'+
  rows.map(o=>'<tr><td>'+esc(o.type)+(o.kind?('/'+esc(o.kind)):'')+'</td><td>'+esc(o.name)+'</td><td><code>'+esc(o.uri)+'</code></td><td>'+esc(o.status||'')+'</td><td><code>'+esc(o.location||'')+'</code></td></tr>').join('')+'</table>';

document.getElementById('view-links').innerHTML = '<table><tr><th>来源</th><th>关系</th><th>目标</th></tr>'+
  D.links.map(l=>'<tr><td>'+esc(l.source)+'</td><td>'+esc(l.type)+'</td><td>'+esc(l.target)+'</td></tr>').join('')+'</table>';

function show(id){
  ['modules','objects','links'].forEach(k=>{
    document.getElementById('view-'+k).style.display = (k===id?'':'none');
    document.getElementById('tab-'+k).classList.toggle('on', k===id);
  });
}
document.getElementById('tab-modules').onclick=()=>show('modules');
document.getElementById('tab-objects').onclick=()=>show('objects');
document.getElementById('tab-links').onclick=()=>show('links');
</script>
</body>
</html>
"""


def render(index, config, out_path):
    """把索引写成自包含 HTML，返回输出路径。"""
    data = {
        "project": index.get("project", {}),
        "objects": index.get("objects", []),
        "links": index.get("links", []),
        "code_root": config.get("code_root", ""),
        "docs_root": config.get("docs_root", ""),
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    return out
