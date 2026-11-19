'use strict';
/* Interactive mission client. All AI algorithms and physics live in Python. */
const $ = (id) => document.getElementById(id);
const canvas = $('warehouseCanvas');
const ctx = canvas.getContext('2d');
const APP = { presets: {}, mission: null, result: null, tool: 'inspect', mode: 'mdp', step: 0, playing: false, timer: null, policy: false, busy: false, dirty: false, canvasBox: null, analysisVersion: 0 };
const COLORS = { lime: '#d2f882', cyan: '#8fdbd0', orange: '#e6b078', text:'#eff0e8', bg:'#131b15' };
let hoveredCell = null;
const poskey = (p) => p[0] + ',' + p[1];
const equal = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];
const has = (list, point) => list.some(p=>equal(p, point));
const pad = (v) => String(v).padStart(3,'0');
let toastHandle = null;
function toast(msg, error=false) { const t=$('toast'); t.textContent=msg;t.classList.toggle('error',error);t.classList.add('visible');clearTimeout(toastHandle);toastHandle=setTimeout(()=>t.classList.remove('visible'),3700); }
function clone(data){return JSON.parse(JSON.stringify(data));}
function setStatus(text) {
  const planning = text === 'PLANNING';
  $('missionStatus').textContent = text;
  $('missionStatus').setAttribute('data-state', planning ? 'planning' : text.includes('FAILED') ? 'error' : text === 'MISSION PLANNED' ? 'ready' : 'idle');
  $('mapLoading').hidden = !planning;
  canvas.setAttribute('aria-busy', String(planning));
  for (const id of ['playBtn', 'backBtn', 'forwardBtn', 'timelineInput', 'policyBtn', 'downloadBtn']) {
    $(id).disabled = planning || !APP.result;
  }
}
function updateCounters(){const m=APP.mission;if(!m)return;$('gridDim').textContent=`${m.width} × ${m.height}`;$('taskNum').textContent=String(m.tasks.length).padStart(2,'0');$('riskNum').textContent=String(m.hazards.length).padStart(2,'0');$('wallNum').textContent=String(m.blocked.length).padStart(2,'0');}
function stop() {
  if (APP.timer !== null) clearInterval(APP.timer);
  APP.timer = null;
  APP.playing = false;
  $('playGlyph').textContent = '▶';
  $('playBtn').setAttribute('aria-pressed', 'false');
}
function routeForMode(){if(!APP.result)return APP.mission ? [APP.mission.start] : [];const r=APP.result;switch(APP.mode){case 'nearest':return r.astar.nearest_route;case 'optimized':return r.astar.optimized_route;case 'shortest':return r.mdp.showcase_shortest.path;default:return r.mdp.showcase.path;}}
function notesForMode(){if(!APP.result)return 'Press RUN AI ANALYSIS to plan the mission.';const r=APP.result;const route=routeForMode();if(APP.step===route.length-1&&APP.step>0){const run=APP.mode==='mdp'?r.mdp.showcase:APP.mode==='shortest'?r.mdp.showcase_shortest:null;return run&&!run.success?'Trial ended before the mission was complete. Review the results or edit the map.':`Mission complete · ${r.mission.tasks.length} picks collected. Robot returned home.`;}if(APP.step===0)return {'nearest':'Nearest-neighbor baseline. A* computes every segment.','optimized':'Hill Climbing improves the order; A* draws the shortest route.','shortest':'Shortest-path baseline under stochastic action outcomes.','mdp':'Risk-aware MDP agent reacts to random deviations.'}[APP.mode];
if(APP.mode==='mdp'||APP.mode==='shortest') {const run=APP.mode==='mdp'?r.mdp.showcase:r.mdp.showcase_shortest;const move=run.trace[APP.step-1];if(move){let activity=move.slipped?'Stochastic deviation. Controller adapts.':'Action '+move.action+' executed.';if(move.hazard)activity+=' Risk tile entered.';return `Step ${APP.step} · ${activity}`;}}
return `Step ${APP.step} / ${route.length-1} · Navigating the warehouse.`;}
function updateTimeline() {
  const lastStep = Math.max(0, routeForMode().length - 1);
  const timeline = $('timelineInput');
  APP.step = Math.max(0, Math.min(APP.step, lastStep));
  timeline.max = String(lastStep);
  timeline.value = String(APP.step);
  const progress = 100 * APP.step / Math.max(1, lastStep);
  timeline.style.background = `linear-gradient(to right, #d2f882 ${progress}%, #3d4634 ${progress}%)`;
  timeline.setAttribute('aria-valuetext', `Step ${APP.step} of ${lastStep}`);
  $('timeStamp').textContent = `${pad(APP.step)} / ${pad(lastStep)} STEPS`;
  $('runComment').lastChild.textContent = ' ' + notesForMode();
  renderBoard();
}
function play() {
  if (!APP.result || APP.busy) return;
  if (APP.playing) {
    stop();
    return;
  }
  const lastStep = routeForMode().length - 1;
  if (APP.step >= lastStep) {
    APP.step = 0;
    updateTimeline();
  }
  APP.playing = true;
  $('playGlyph').textContent = 'Ⅱ';
  $('playBtn').setAttribute('aria-pressed', 'true');
  APP.timer = setInterval(() => {
    APP.step++;
    updateTimeline();
    if (APP.step >= lastStep) stop();
  }, Number($('speedSelect').value));
}
function selectScenario(id){const preset=APP.presets[id];if(!preset)return;APP.analysisVersion++;APP.busy=false;$('runBtn').disabled=false;$('runLabel').textContent='RUN AI ANALYSIS';stop();APP.mission=clone(preset);APP.result=null;APP.step=0;APP.dirty=false;APP.policy=false;hoveredCell=null;$('warehouseTitle').textContent=preset.name;$('policyBtn').classList.remove('selected');$('policyBtn').setAttribute('aria-pressed','false');$('scenarioDescription').textContent=preset.description;updateCounters();$('dirtyText').textContent='PRESET LOADED';clearResults();resizeBoard();}
function clearResults(){['baseSteps','optSteps','savingPct','riskReduction','riskBase','riskMdp','comparisonSteps','successRate','sweeps','recoveryCells'].forEach(id=>$(id).textContent='—');$('savingLabel').textContent='Compared with baseline';$('riskReductionUnit').textContent='%';$('riskReductionLabel').textContent='MDP vs shortest-path controller';$('barBase').style.width='0%';$('barMdp').style.width='0%';$('orderPills').innerHTML='<span class="order-placeholder">Waiting for analysis</span>';setStatus('NOT ANALYZED');updateTimeline();}
async function analyze(){if(!APP.mission||APP.busy)return;
const version=++APP.analysisVersion;
const snapshot=clone(APP.mission); // the result must match precisely the mission submitted
stop();APP.busy=true;$('runBtn').disabled=true;$('runLabel').textContent='COMPUTING…';setStatus('PLANNING');$('dirtyText').textContent='RUNNING MODELS';
try{const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot)});const body=await response.json();
if(version!==APP.analysisVersion)return; // ignore responses for a scenario that has since changed
if(!response.ok)throw new Error(body.error||'Analysis failed.');
APP.result=body;APP.dirty=false;APP.step=0;setStatus('MISSION PLANNED');$('dirtyText').textContent='MODELS CONVERGED';updateAnalytics();updateTimeline();}
catch(e){if(version!==APP.analysisVersion)return;APP.result=null;APP.policy=false;$('policyBtn').classList.remove('selected');$('policyBtn').setAttribute('aria-pressed','false');clearResults();setStatus('PLAN FAILED');$('dirtyText').textContent='CHECK MISSION';toast(e.message||String(e),true);}
finally{if(version===APP.analysisVersion){APP.busy=false;$('runBtn').disabled=false;$('runLabel').textContent='RUN AI ANALYSIS';}}}
function updateAnalytics(){const r=APP.result;if(!r)return;const h=r.hill_climbing,b=r.mdp.shortest_controller,a=r.mdp.risk_aware_controller;
$('baseSteps').textContent=h.nearest_steps;$('optSteps').textContent=h.optimized_steps;$('savingPct').textContent=h.improvement_pct.toFixed(1);$('savingLabel').textContent=`${h.nearest_steps-h.optimized_steps} planned grid steps saved`;
const riskReduction=b.mean_hazard_entries>0?100*(b.mean_hazard_entries-a.mean_hazard_entries)/b.mean_hazard_entries:(a.mean_hazard_entries>0?null:0);
$('riskReduction').textContent=riskReduction===null?'N/A':riskReduction.toFixed(1);$('riskReductionUnit').textContent=riskReduction===null?'':'%';$('riskReductionLabel').textContent=riskReduction===null?'Baseline has zero risk entries; percentage undefined':riskReduction<0?'MDP increased exposure vs shortest-path control':'MDP vs shortest-path controller';$('riskBase').textContent=b.mean_hazard_entries.toFixed(2);$('riskMdp').textContent=a.mean_hazard_entries.toFixed(2);
const max=Math.max(b.mean_hazard_entries,a.mean_hazard_entries,0.01);$('barBase').style.width=`${100*b.mean_hazard_entries/max}%`;$('barMdp').style.width=`${100*a.mean_hazard_entries/max}%`;
$('comparisonSteps').textContent=`${b.mean_steps.toFixed(1)} vs ${a.mean_steps.toFixed(1)}`;$('successRate').textContent=`${a.success_rate.toFixed(1)}%`;$('sweeps').textContent=r.mdp.value_iteration_sweeps.toLocaleString();$('recoveryCells').textContent=r.mdp.properness_corrections.toLocaleString();
const order=$('orderPills');order.replaceChildren();const sequence=['H',...h.optimized_order.map(String),'H'];sequence.forEach((value,i)=>{if(i){const arrow=document.createElement('span');arrow.className='order-arrow';arrow.textContent='→';order.appendChild(arrow);}const pill=document.createElement('span');pill.className='order-node'+(value==='H'?' depot':'');pill.textContent=value;const x=value==='H'?r.mission.start:r.mission.tasks[Number(value)-1];pill.title=value==='H'?'Depot':`Pick ${value} (${x[0]}, ${x[1]})`;order.appendChild(pill);});}
function toggleTool(tool){APP.tool=tool;document.querySelectorAll('.tool').forEach(b=>{b.classList.toggle('active',b.dataset.tool===tool);b.setAttribute('aria-pressed',String(b.dataset.tool===tool));});canvas.style.cursor=tool==='inspect'?'crosshair':tool==='erase'?'cell':'copy';renderBoard();}
function editCell(cell){const m=APP.mission;if(!m||APP.busy)return;if(APP.tool==='inspect'){let status=equal(cell,m.start)?'Depot':has(m.tasks,cell)?'Pick location':has(m.blocked,cell)?'Shelf':has(m.hazards,cell)?'Hazard':'Empty floor';toast(`Cell (${cell[0]}, ${cell[1]}) — ${status}`);return;}
if(equal(cell,m.start)){toast('The home depot cannot be edited.',true);return;}
const remove=(list)=>{const i=list.findIndex(p=>equal(p,cell));if(i>=0){list.splice(i,1);return true;}return false;};
if (APP.tool === 'erase') {
  const removedTask = remove(m.tasks);
  const removedShelf = remove(m.blocked);
  const removedHazard = remove(m.hazards);
  if (!removedTask && !removedShelf && !removedHazard) return;
} else if(APP.tool==='task') {if(!remove(m.tasks)){if(m.tasks.length>=8){toast('At most 8 pick locations are supported.',true);return;}remove(m.blocked);remove(m.hazards);m.tasks.push(cell);}}
else if(APP.tool==='shelf'){if(!remove(m.blocked)){remove(m.tasks);remove(m.hazards);m.blocked.push(cell);}}
else if(APP.tool==='hazard'){if(!remove(m.hazards)){remove(m.tasks);remove(m.blocked);m.hazards.push(cell);}}
stop();APP.analysisVersion++;APP.result=null;APP.dirty=true;APP.step=0;APP.policy=false;$('policyBtn').classList.remove('selected');$('policyBtn').setAttribute('aria-pressed','false');clearResults();updateCounters();$('dirtyText').textContent='UNSAVED MAP CHANGES';setStatus('REPLAN REQUIRED');renderBoard();}
function updateCanvasSize(){if(!APP.mission)return;const available=canvas.parentElement.clientWidth-24;const ratio=(APP.mission.height+1.2)/(APP.mission.width+1.2);const cssW=Math.max(150,available);const cssH=Math.round(cssW*ratio);canvas.style.width=cssW+'px';canvas.style.height=cssH+'px';const dpi=Math.min(2,window.devicePixelRatio||1);canvas.width=Math.round(cssW*dpi);canvas.height=Math.round(cssH*dpi);ctx.setTransform(dpi,0,0,dpi,0,0);APP.canvasBox={x:14,y:14,w:cssW-28,h:cssH-28,cw:(cssW-28)/APP.mission.width,ch:(cssH-28)/APP.mission.height};}
function resizeBoard(){updateCanvasSize();renderBoard();}
function pxy(p){const b=APP.canvasBox;return [b.x+(p[0]+.5)*b.cw,b.y+(p[1]+.5)*b.ch];}
function roundRect(x,y,w,h,r,fill){if(w<=0||h<=0)return;ctx.beginPath();ctx.roundRect(x,y,w,h,Math.min(r,w/2,h/2));ctx.fillStyle=fill;ctx.fill();}
function routeLine(route,color,alpha=1,width=3,dashes=[]){if(!route||route.length<2)return;ctx.save();ctx.beginPath();route.forEach((p,i)=>{const [x,y]=pxy(p);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.lineCap='round';ctx.lineJoin='round';ctx.setLineDash(dashes);ctx.strokeStyle=color;ctx.globalAlpha=alpha;ctx.lineWidth=width;ctx.shadowBlur=width>3?13:0;ctx.shadowColor=color;ctx.stroke();ctx.restore();}
function renderBoard(){if(!APP.mission||!APP.canvasBox)return;const m=APP.mission,b=APP.canvasBox;ctx.clearRect(0,0,canvas.width,canvas.height);const wall=new Set(m.blocked.map(poskey)),hazard=new Set(m.hazards.map(poskey));
// Subtle reference coordinates give the floor the feel of a technical plan.
ctx.font=`${Math.max(6,Math.min(9,b.cw*.25))}px Consolas, monospace`;ctx.fillStyle='#738967';ctx.textAlign='center';ctx.textBaseline='middle';
for(let x=0;x<m.width;x+=2)ctx.fillText(String(x).padStart(2,'0'),b.x+(x+.5)*b.cw,6);
for(let y=0;y<m.height;y+=2)ctx.fillText(String(y).padStart(2,'0'),6,b.y+(y+.5)*b.ch);
for(let y=0;y<m.height;y++)for(let x=0;x<m.width;x++){
const k=x+','+y,px=b.x+x*b.cw+1,py=b.y+y*b.ch+1,w=b.cw-2,h=b.ch-2;
if(wall.has(k)){
roundRect(px,py+1,w,h,2,'#2b3729');roundRect(px,py,w,h-1,2,'#4a5940');
const inset=Math.max(2,w*.14);roundRect(px+inset,py+inset,w-2*inset,h-2*inset,1,'#56664b');
ctx.fillStyle='#8c9b77';ctx.globalAlpha=.45;ctx.fillRect(px+inset,py+inset,Math.max(1,w-2*inset),1);ctx.globalAlpha=1;
ctx.fillStyle='#2d3928';ctx.fillRect(px+w*.48,py+inset,1,Math.max(1,h-2*inset));
}
else if(hazard.has(k)){
roundRect(px,py,w,h,2,'#4c3a23');ctx.save();ctx.strokeStyle='#e6b078';ctx.globalAlpha=.55;ctx.lineWidth=1;
for(let i=0;i<3;i++){const offset=(i+1)/4;ctx.beginPath();ctx.moveTo(px+2,py+h*offset);ctx.lineTo(px+w*offset,py+2);ctx.stroke();}ctx.restore();
}
else{roundRect(px,py,w,h,2,(x+y)%2===0?'#1d2a1d':'#1c281c');}
}
if(hoveredCell&&!APP.busy){const [hx,hy]=hoveredCell;const color=APP.tool==='hazard'?COLORS.orange:APP.tool==='task'?COLORS.cyan:COLORS.lime;ctx.save();ctx.globalAlpha=.17;roundRect(b.x+hx*b.cw,b.y+hy*b.ch,b.cw,b.ch,3,color);ctx.globalAlpha=.8;ctx.strokeStyle=color;ctx.lineWidth=1;ctx.stroke();ctx.restore();}
if(APP.result){let route=routeForMode();let color=APP.mode==='mdp'?COLORS.cyan:APP.mode==='shortest'?COLORS.orange:APP.mode==='optimized'?COLORS.lime:'#a6b699';routeLine(route,color,.32,2,[3,4]);routeLine(route.slice(0,Math.max(1,APP.step+1)),color,1,3);if(APP.step>0){const [sx,sy]=pxy(route[APP.step]);ctx.fillStyle=color+'25';ctx.beginPath();ctx.arc(sx,sy,Math.min(b.cw,b.ch)*.45,0,Math.PI*2);ctx.fill();}
if(APP.policy&&APP.mode==='mdp'){const symbol={N:'↑',E:'→',S:'↓',W:'←'};ctx.save();ctx.fillStyle='#d1f39b';ctx.globalAlpha=.58;ctx.font=`${Math.max(9,Math.min(16,b.ch*.44))}px monospace`;ctx.textAlign='center';ctx.textBaseline='middle';const trace=APP.result.mdp.showcase.trace;const activeLeg=trace.length?Math.min(APP.result.mdp.policy_by_leg.length-1,(trace[Math.min(APP.step,trace.length-1)]||{}).leg||0):0;const field=APP.result.mdp.policy_by_leg[activeLeg].cells;for(const p of field){if(has(m.tasks,[p.x,p.y])||equal([p.x,p.y],m.start))continue;ctx.fillText(symbol[p.action]||'',...pxy([p.x,p.y]));}ctx.restore();}}
// Highlight all requested pick locations (initial numbering, not visit order)
m.tasks.forEach((task,i)=>{const [x,y]=pxy(task);const r=Math.max(5,Math.min(b.cw,b.ch)*.35);ctx.save();ctx.shadowColor='#8fdbd033';ctx.shadowBlur=10;ctx.fillStyle='#234239';ctx.strokeStyle=COLORS.cyan;ctx.lineWidth=1.4;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.restore();ctx.font=`600 ${Math.min(13,r*1.15)}px Segoe UI, sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#c3f3e4';ctx.fillText(String(i+1),x,y+.3);});
// Home depot
{const [x,y]=pxy(m.start);const s=Math.min(b.cw,b.ch)*.76;roundRect(x-s/2,y-s/2,s,s,Math.min(5,s*.2),COLORS.lime);ctx.fillStyle='#243917';ctx.font=`700 ${Math.max(7,s*.58)}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('H',x,y+.5);}
// The robot is drawn last so it remains legible above the path and task markers.
if(APP.result){const route=routeForMode(),point=route[APP.step]||m.start;const [x,y]=pxy(point);const r=Math.min(b.cw,b.ch)*.24;ctx.save();ctx.shadowColor='#d2f88277';ctx.shadowBlur=12;ctx.fillStyle='#f2f6e9';ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle='#283d1d';ctx.lineWidth=1.8;ctx.stroke();ctx.fillStyle='#405b2c';ctx.beginPath();ctx.arc(x,y,r*.32,0,Math.PI*2);ctx.fill();ctx.restore();}
}
function atCanvas(e){if(!APP.canvasBox)return null;const rect=canvas.getBoundingClientRect(),sx=(e.clientX-rect.left),sy=(e.clientY-rect.top),b=APP.canvasBox;const x=Math.floor((sx-b.x)/b.cw),y=Math.floor((sy-b.y)/b.ch);if(x<0||y<0||x>=APP.mission.width||y>=APP.mission.height)return null;return [x,y];}
canvas.addEventListener('click',(e)=>{const p=atCanvas(e);if(p)editCell(p);});
canvas.addEventListener('mousemove',(e)=>{const p=atCanvas(e),t=$('cellTooltip');if(!equal(p,hoveredCell)){hoveredCell=p;renderBoard();}if(!p){t.hidden=true;return;}const m=APP.mission;const type=equal(p,m.start)?'DEPOT':has(m.tasks,p)?'PICK '+(1+m.tasks.findIndex(x=>equal(p,x))):has(m.blocked,p)?'SHELF':has(m.hazards,p)?'SLIPPERY':'FLOOR';t.textContent=`${type}  /  X:${p[0]} Y:${p[1]}`;t.hidden=false;const bounding=canvas.parentElement.getBoundingClientRect();t.style.left=Math.max(12,Math.min(bounding.width-170,e.clientX-bounding.left+12))+'px';t.style.top=Math.max(8,e.clientY-bounding.top-34)+'px';});
canvas.addEventListener('mouseleave',()=>{$('cellTooltip').hidden=true;hoveredCell=null;renderBoard();});
function exportResults(){if(!APP.result){toast('Analyze first before exporting.',true);return;}const file=new Blob([JSON.stringify(APP.result,null,2)],{type:'application/json'});const url=URL.createObjectURL(file);const anchor=document.createElement('a');anchor.href=url;anchor.download='aisle-ai-mission-results.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),2000);toast('Mission analysis exported as JSON.');}
function register() {
  document.querySelectorAll('.tool').forEach(button => {
    button.addEventListener('click', () => toggleTool(button.dataset.tool));
  });
  $('presetSelect').addEventListener('change', event => { selectScenario(event.target.value); analyze(); });
  $('runBtn').addEventListener('click', analyze);
  $('resetBtn').addEventListener('click', () => { selectScenario($('presetSelect').value); analyze(); });
  $('viewSelect').addEventListener('change', event => {
    stop();
    APP.mode = event.target.value;
    APP.step = 0;
    if (APP.mode !== 'mdp') {
      APP.policy = false;
      $('policyBtn').classList.remove('selected');
      $('policyBtn').setAttribute('aria-pressed', 'false');
    }
    updateTimeline();
  });
  $('playBtn').addEventListener('click', play);
  $('backBtn').addEventListener('click', () => { stop(); APP.step--; updateTimeline(); });
  $('forwardBtn').addEventListener('click', () => { stop(); APP.step++; updateTimeline(); });
  $('timelineInput').addEventListener('input', event => { stop(); APP.step = Number(event.target.value); updateTimeline(); });
  $('speedSelect').addEventListener('change', () => {
    if (APP.playing) {
      stop();
      play();
    }
  });
  $('downloadBtn').addEventListener('click', exportResults);
  $('policyBtn').addEventListener('click', () => {
    if (!APP.result || APP.busy) return;
    APP.policy = !APP.policy;
    if (APP.policy) {
      toast('Arrows show MDP actions, including reachability recovery when needed.');
      if (APP.mode !== 'mdp') {
        stop();
        $('viewSelect').value = 'mdp';
        APP.mode = 'mdp';
        APP.step = 0;
        updateTimeline();
      }
    }
    $('policyBtn').classList.toggle('selected', APP.policy);
    $('policyBtn').setAttribute('aria-pressed', String(APP.policy));
    renderBoard();
  });
  window.addEventListener('resize', resizeBoard);
  window.addEventListener('keydown', event => {
    if (event.code === 'Space' && APP.result && !APP.busy
        && !['INPUT', 'SELECT', 'BUTTON'].includes(event.target.tagName)) {
      event.preventDefault();
      play();
    }
  });
}
async function initialize(){setStatus('STANDBY');register();try{const response=await fetch('/api/presets');if(!response.ok)throw Error('Cannot load presets.');const data=await response.json();APP.presets=data.presets;selectScenario('standard');await analyze();}catch(e){setStatus('CONNECTION FAILED');toast('Start the Python server: python run.py',true);}}
initialize();
