"""HTML-страницы (без шаблонизатора): строки + html.escape."""
from html import escape as E

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--tx:#1b1f24;--mut:#5b6573;--bd:#d0d7de;--ac:#2563eb;--err:#b42318}
[data-theme=dark]{--bg:#14171c;--card:#1d222a;--tx:#e8ebf0;--mut:#a3adbb;--bd:#364050;--ac:#6ea0ff;--err:#ff8a80}
*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--tx)}
header{display:flex;gap:16px;align-items:center;padding:12px 20px;background:var(--card);border-bottom:1px solid var(--bd)}
header b{flex:1}a{color:var(--ac)}main{max-width:980px;margin:20px auto;padding:0 16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:18px;margin-bottom:16px}
label{display:block;font-size:14px;color:var(--mut);margin:10px 0 4px}
input,select,textarea,button{font:inherit;color:var(--tx);background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;max-width:100%}
input[type=color]{padding:2px;height:38px;width:60px}textarea,input[type=text],input[type=email],input[type=password]{width:100%}
button{cursor:pointer}button.pri{background:var(--ac);color:#fff;border-color:var(--ac)}button:disabled{opacity:.45;cursor:not-allowed}
.row{display:flex;gap:12px;flex-wrap:wrap}.row>*{flex:1;min-width:140px}.err{color:var(--err)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid var(--bd);text-align:left}
"""


def layout(body, user=None):
    nav = ('<a href="/history">История</a><span class="mut">%s</span><button type="button" id="theme">Тёмная тема</button>'
           '<a href="/logout">Выйти</a>' % E(user)) if user else '<a href="/login">Вход</a><a href="/register">Регистрация</a>'
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>QR-генератор</title>'
            "<script>try{document.documentElement.dataset.theme=localStorage.getItem('theme')||'light'}catch(e){}</script>"
            "<style>" + CSS + "</style></head><body><header><b>QR-генератор</b><a href=\"/\">Генератор</a>" + nav +
            "</header><main>" + body + "</main><script>"
            "const tb=document.getElementById('theme');if(tb)tb.onclick=()=>{const d=document.documentElement,"
            "t=d.dataset.theme==='dark'?'light':'dark';d.dataset.theme=t;try{localStorage.setItem('theme',t)}catch(e){}};"
            "</script></body></html>")


def auth_page(mode, err=None):
    reg = mode == "register"
    return ('<div class="card" style="max-width:400px;margin:auto"><h2>%s</h2>%s<form method="post">'
            '<label for="email">Email</label><input id="email" type="email" name="email" required>'
            '<label for="pw">Пароль</label><input id="pw" type="password" name="password" required minlength="6">'
            '<p><button class="pri">%s</button></p></form></div>') % (
        "Регистрация" if reg else "Вход", '<p class="err" role="alert">%s</p>' % E(err) if err else "",
        "Создать аккаунт" if reg else "Войти")


def history_page(rows):
    if not rows:
        return '<div class="card"><h2>История (последние 50)</h2><p class="mut">Нет сохранённых кодов</p></div>'
    tr = "".join('<tr><td>%s</td><td><a href="/history/%d">%s</a></td><td><form method="post" action="/history/%d/delete">'
                 '<button>Удалить</button></form></td></tr>' % (E(r["created_at"]), r["id"], E(r["label"][:80]), r["id"])
                 for r in rows)
    return ('<div class="card"><h2>История (последние 50)</h2><p><a href="/history.csv">Выгрузить всю историю в CSV</a></p>'
            '<table><tr><th>Дата</th><th>Текст</th><th></th></tr>%s</table></div>' % tr)


def item_page(r):
    i = r["id"]
    return ('<div class="card"><h2>%s</h2><p class="mut">%s</p><img src="/history/%d/file.png" alt="QR-код" '
            'style="max-width:100%%;image-rendering:pixelated"><p><a href="/history/%d/file.png?dl=1"><button>Скачать PNG</button></a> '
            '<a href="/history/%d/file.svg?dl=1"><button>Скачать SVG</button></a> <a href="/history">← к истории</a></p></div>'
            % (E(r["label"]), E(r["created_at"]), i, i, i))


INDEX = """
<div class="row" style="margin-bottom:12px;flex:none"><button type="button" id="tab-gen" class="pri">Генератор</button>
<button type="button" id="tab-stat">Статистика</button></div>
<div id="pane-stat" class="card" hidden><h2>Статистика</h2><p>Создано QR-кодов на этом устройстве: <b id="stat-n">0</b></p>
<p class="mut">Считается по локальной истории браузера, без регистрации.</p></div>
<div id="pane-gen" class="row" style="align-items:flex-start">
<form id="f" class="card" autocomplete="off" onsubmit="return false">
<label>Тип данных</label><select name="kind"><option value="text">Ссылка / текст</option><option value="wifi">Wi-Fi</option><option value="contact">Контакт</option></select>
<div data-kind="text"><label for="text">Ссылка или текст (до __MAX__ символов)</label><textarea id="text" name="text" rows="4"></textarea></div>
<div data-kind="wifi" hidden><label>SSID</label><input type="text" name="ssid"><label>Пароль</label><input type="text" name="password">
<label>Защита</label><select name="enc"><option>WPA</option><option>WEP</option><option value="nopass">Без пароля</option></select></div>
<div data-kind="contact" hidden><label>Имя</label><input type="text" name="c_name"><label>Телефон</label><input type="text" name="c_phone">
<label>Email</label><input type="text" name="c_email"></div>
<div class="row"><div><label>Коррекция ошибок</label><select name="ec"><option>L</option><option selected>M</option><option>Q</option><option>H</option></select></div>
<div><label>Маска</label><select name="mask"><option value="auto">Авто</option><option>0</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option><option>6</option><option>7</option></select></div>
<div><label>Размер</label><select name="size"><option>200</option><option selected>500</option><option>1000</option></select></div></div>
<div class="row"><div><label>Цвет модулей</label><input type="color" name="fg" value="#000000"></div>
<div><label>Цвет фона</label><input type="color" name="bg" value="#ffffff"></div>
<div><label>Формат</label><select name="fmt"><option value="png">PNG</option><option value="svg">SVG</option></select></div></div>
<label>Подпись под кодом (до 60 символов)</label><input type="text" name="caption" maxlength="60">
<label><input type="checkbox" name="frame"> Рамка</label>
<label>Логотип в центре (PNG до 1024×1024; включается уровень H)</label><input type="file" id="logo" accept="image/png">
__TPL__
<p><button type="button" class="pri" id="gen" disabled>Сгенерировать</button></p></form>
<div class="card" style="flex:1;min-width:280px"><div id="ph" class="mut">Введите текст</div>
<p id="msg" class="err" role="alert" hidden></p><img id="img" alt="QR-код" hidden style="max-width:100%;image-rendering:pixelated">
<p><button type="button" id="dl-png" disabled>Скачать PNG</button>
<button type="button" id="dl-svg" disabled __SVGTITLE__>Скачать SVG</button></p>
<hr style="border:0;border-top:1px solid var(--bd)">
<p><b>Пакетная генерация</b> <span class="mut">CSV с колонкой <code>text</code>, до 500 строк → ZIP с PNG (настройки — из формы слева)</span></p>
<input type="file" id="csv" accept=".csv,text/csv"> <button type="button" id="batch">Получить ZIP</button><p id="bmsg" class="mut"></p></div></div>
<script>
const F=document.getElementById('f'),$=id=>document.getElementById(id),V=n=>F.elements[n].value;
const LOGGED=__LOGGED__;let seq=0,timer,ok=false,logo='';
const KEYS=['fg','bg','size','fmt','ec','mask'];
function body(){const o={};for(const el of F.elements){if(!el.name)continue;o[el.name]=el.type==='checkbox'?el.checked:el.value;}o.logo=logo;return o;}
const post=(url,obj)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});
function emptyMsg(){const k=V('kind');
 if(k==='text')return V('text').trim()?'':'Введите текст';
 if(k==='wifi')return V('ssid').trim()?'':'Введите SSID';
 return (V('c_name')+V('c_phone')+V('c_email')).trim()?'':'Заполните хотя бы одно поле';}
function setOk(v){ok=v;$('dl-png').disabled=!v;$('dl-svg').disabled=!v||!LOGGED;}
function show(err,ph){$('img').hidden=true;$('msg').hidden=!err;$('msg').textContent=err||'';$('ph').hidden=!ph;$('ph').textContent=ph||'';setOk(false);}
async function run(save){
 const my=++seq,e=emptyMsg();$('gen').disabled=!!e;
 if(e){show('',e);return;}
 if(V('fg').toLowerCase()===V('bg').toLowerCase()){show('QR-код будет нечитаем: цвета модулей и фона совпадают');return;}
 try{const r=await post(save?'/api/generate':'/api/preview',body());const j=await r.json();if(my!==seq)return;
  if(!j.ok){show(j.error);return;}
  $('msg').hidden=true;$('ph').hidden=true;$('img').src=j.image;$('img').hidden=false;setOk(true);if(save)localAdd(j.label,j.size,j.fmt);
 }catch(x){if(my===seq)show('Нет связи с сервером');}}
function schedule(){setOk(false);clearTimeout(timer);timer=setTimeout(()=>run(false),350);}
function getLocal(){try{return JSON.parse(localStorage.getItem('qr_local')||'[]')}catch(e){return[]}}
function localAdd(t,s,f,n){const a=getLocal();for(let i=0;i<(n||1);i++)a.push({t:new Date().toISOString(),text:t,size:s,fmt:f});
 try{localStorage.setItem('qr_local',JSON.stringify(a.slice(-1000)))}catch(e){}}
function kindUI(){document.querySelectorAll('[data-kind]').forEach(d=>d.hidden=d.dataset.kind!==V('kind'));}
F.addEventListener('input',schedule);F.addEventListener('change',()=>{kindUI();schedule();});
$('logo').onchange=e=>{const f=e.target.files[0];if(!f){logo='';schedule();return;}
 const rd=new FileReader();rd.onload=()=>{logo=rd.result;schedule();};rd.readAsDataURL(f);};
$('gen').onclick=()=>run(true);
function save(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function dl(fmt){const r=await post('/download?fmt='+fmt,body());if(!r.ok){alert((await r.json()).error);return;}save(await r.blob(),'qr.'+fmt);}
$('dl-png').onclick=()=>dl('png');$('dl-svg').onclick=()=>dl('svg');
$('batch').onclick=async()=>{const f=$('csv').files[0],m=$('bmsg');m.className='mut';
 if(!f){m.textContent='Выберите CSV-файл';return;}m.textContent='Обработка…';
 const o=body();o.logo='';o.csv=await f.text();
 const r=await post('/batch',o);if(!r.ok){m.className='err';m.textContent=(await r.json()).error;return;}
 save(await r.blob(),'qr_codes.zip');const n=+r.headers.get('X-Generated');
 m.textContent='Готово: '+n+' шт., пропущено строк: '+r.headers.get('X-Skipped');localAdd('(CSV)',V('size'),'png',n);};
function tab(st){$('pane-gen').hidden=st;$('pane-stat').hidden=!st;$('tab-gen').className=st?'':'pri';$('tab-stat').className=st?'pri':'';
 if(st)$('stat-n').textContent=getLocal().length;}
$('tab-gen').onclick=()=>tab(false);$('tab-stat').onclick=()=>tab(true);
if(LOGGED){const sel=$('tpl');let T=[];
 const load=async()=>{const j=await(await fetch('/api/templates')).json();T=j.templates||[];
  sel.innerHTML='<option value="">— шаблон —</option>';T.forEach((t,i)=>{const o=document.createElement('option');o.value=i;o.textContent=t.name;sel.appendChild(o);});};
 sel.onchange=()=>{if(sel.value==='')return;const s=T[+sel.value].settings;for(const k of KEYS)if(k in s)F.elements[k].value=s[k];schedule();};
 $('tpl-save').onclick=async()=>{const name=prompt('Имя шаблона');if(!name)return;const s={};for(const k of KEYS)s[k]=V(k);
  const j=await(await post('/api/templates',{name,settings:s})).json();if(!j.ok)alert(j.error);else load();};load();}
kindUI();run(false);
</script>
"""

TPL = ('<div class="row" style="margin-top:12px"><select id="tpl"><option value="">— шаблон —</option></select>'
       '<button type="button" id="tpl-save">Сохранить как шаблон</button></div>')


def index_page(user, max_text):
    return (INDEX.replace("__MAX__", str(max_text)).replace("__TPL__", TPL if user else "")
            .replace("__LOGGED__", "true" if user else "false")
            .replace("__SVGTITLE__", "" if user else 'title="SVG — только для зарегистрированных"'))
