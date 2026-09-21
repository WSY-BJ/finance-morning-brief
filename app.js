'use strict';
const byId = id => document.getElementById(id);
const make = (tag, className, value) => {const el=document.createElement(tag); if(className)el.className=className; if(value !== undefined)el.textContent=String(value); return el;};
let report, current = 0, startX = null;
const safeURL = value => {try{const u=new URL(value); return u.protocol==='https:' ? u.href : null;}catch{return null;}};
function listBlock(block, holder) {
  const list=make('ul','bullets'); (block.items||[]).forEach(item => list.append(make('li','',item))); holder.append(list);
}
function renderBlock(block, page){
  const wrapper=make('section','block');
  if(block.type==='notice')wrapper.className='notice'+(block.tone==='warning'?' warning':'');
  if(block.title)wrapper.append(make('h3','',block.title));
  switch(block.type){
    case 'notice': wrapper.append(make('p','',block.text)); break;
    case 'bullets': listBlock(block,wrapper);break;
    case 'chain': {
      const chain=make('div','chain'); (block.items||[]).forEach((item,i)=>{if(i)chain.append(make('span','chain-arrow','→'));chain.append(make('span','chain-step',item));});wrapper.append(chain);break;
    }
    case 'metricGrid': {
      const grid=make('div','metric-grid');(block.items||[]).forEach(item=>{const m=make('div','metric');m.append(make('div','metric-label',item.label),make('div','metric-value',item.value),make('div','metric-note',item.note));grid.append(m);});wrapper.append(grid);break;
    }
    case 'research': {
      wrapper.className='research'; [['思路',block.thesis],['验证',block.verify],['风险',block.risk]].forEach(([label,value])=>{const row=make('div','minirow');row.append(make('b','',label),make('span','',value));wrapper.append(row);});break;
    }
    case 'formula': wrapper.append(make('div','formula',block.expression),make('p','',block.note));break;
    case 'quiz': {
      wrapper.append(make('p','',block.question));const btn=make('button','reveal','显示答案');btn.type='button';btn.setAttribute('aria-expanded','false');const answer=make('p','answer',block.answer);answer.hidden=true;btn.addEventListener('click',()=>{answer.hidden=!answer.hidden;btn.textContent=answer.hidden?'显示答案':'收起答案';btn.setAttribute('aria-expanded',String(!answer.hidden));});wrapper.append(btn,answer);break;
    }
    default: wrapper.append(make('p','','未知栏目格式，已略过。'));
  }
  page.append(wrapper);
}
function render(){
  byId('edition').textContent=report.edition||'晨报';
  byId('state').textContent=report.status==='published'?'已发布 · 延迟行情':'样刊 · 非实时';
  byId('date').textContent=report.date||'非正式行情版本';
  byId('headline').textContent=report.title||'今日晨报';
  byId('subtitle').textContent=report.subtitle||'';
  byId('intro').textContent=report.intro||'';
  const tabs=byId('tabs'),pages=byId('pages');tabs.replaceChildren();pages.replaceChildren();
  report.pages.forEach((data,i)=>{
    const tab=make('button','tab',data.title);tab.type='button';tab.setAttribute('role','tab');tab.setAttribute('aria-controls','page-'+i);tab.addEventListener('click',()=>go(i));tabs.append(tab);
    const page=make('article','page');page.id='page-'+i;page.setAttribute('role','tabpanel');page.append(make('p','page-eyebrow',data.eyebrow||String(i+1)),make('h2','page-title',data.title),make('p','page-lead',data.lead||''));
    (data.blocks||[]).forEach(block=>renderBlock(block,page));pages.append(page);
  });
  const sources=byId('sources');sources.replaceChildren(); if(report.sources&&report.sources.length){sources.append(make('h3','','本期来源 · 原始链接'));const ul=make('ul','');report.sources.forEach(s=>{const url=safeURL(s.url);if(!url)return;const li=make('li','');const a=make('a','',s.title);a.href=url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);if(s.asOf)li.append(make('span','',' · '+s.asOf));ul.append(li);});sources.append(ul);}else{sources.append(make('p','footnote','样刊没有引用当日新闻或行情。'));}
  const hash=location.hash.slice(1);const initial=report.pages.findIndex(p=>p.id===hash);go(initial>=0?initial:0,false);
}
function go(index,scroll=true){if(!report)return;current=Math.max(0,Math.min(index,report.pages.length-1));const tabs=[...byId('tabs').children];[...byId('pages').children].forEach((p,i)=>{p.hidden=i!==current;tabs[i].setAttribute('aria-selected',String(i===current));});tabs[current].scrollIntoView({block:'nearest',inline:'nearest'});byId('progress-label').textContent=String(current+1).padStart(2,'0')+' / '+String(report.pages.length).padStart(2,'0');byId('progress-fill').style.width=((current+1)/report.pages.length*100)+'%';byId('previous').disabled=current===0;byId('next').disabled=current===report.pages.length-1;history.replaceState(null,'','#'+report.pages[current].id);if(scroll)window.scrollTo({top:0,behavior:'smooth'});}
byId('previous').addEventListener('click',()=>go(current-1));byId('next').addEventListener('click',()=>go(current+1));
byId('pages').addEventListener('touchstart',event=>{startX=event.touches[0]?.clientX??null;},{passive:true});
byId('pages').addEventListener('touchend',event=>{if(startX===null)return;const diff=(event.changedTouches[0]?.clientX??startX)-startX;startX=null;if(Math.abs(diff)>75)go(current+(diff<0?1:-1));},{passive:true});
document.addEventListener('keydown',event=>{if(event.key==='ArrowRight')go(current+1);if(event.key==='ArrowLeft')go(current-1);});
fetch('report.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('状态码 '+r.status);return r.json();}).then(json=>{if(!Array.isArray(json.pages)||!json.pages.length)throw Error('晨报内容格式错误');report=json;render();}).catch(error=>{const el=make('div','error','晨报未加载成功，请检查网络或稍后重试。已停止展示旧数据。');byId('pages').replaceChildren(el);byId('intro').textContent='加载失败：'+error.message;byId('edition').textContent='暂不可用';byId('previous').disabled=true;byId('next').disabled=true;});
