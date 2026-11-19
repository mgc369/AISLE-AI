/* Dependency-free frontend smoke test (Node.js 18+).
 * Simulates DOM/canvas without a browser. Does not replace visual browser QA.
 * Run from the project root: node tests/test_web_client.js
 */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const child_process=require('child_process');
const path=require('path');
const ROOT=path.resolve(__dirname,'..');
const model=child_process.execFileSync('python',['-c',`import json;from engine.algorithms import analyze_mission;from engine.scenarios import scenarios;print(json.dumps({'presets':scenarios(),'analysis':{k:analyze_mission(v,trials=60) for k,v in scenarios().items()}}))`],{cwd:ROOT,encoding:'utf-8',maxBuffer:10*1024*1024});
const fixture=JSON.parse(model);
class FakeClassList{constructor(){this.classes=new Set()} add(x){this.classes.add(x)} remove(x){this.classes.delete(x)} toggle(x,on){if(on===undefined)on=!this.classes.has(x);on?this.classes.add(x):this.classes.delete(x);return on}contains(x){return this.classes.has(x)}}
class FakeNode{constructor(tag='div',id=''){this.tagName=tag.toUpperCase();this.id=id;this._children=[];this.children=this._children;this.textContent='';this.innerHTML='';this.style={};this.classList=new FakeClassList();this.listeners={};this.attributes={};this.dataset={};this.value='';this.disabled=false;this.hidden=false;this.lastChild={textContent:''};this.clientWidth=900;this.parentElement=null;}
 addEventListener(event,fn){this.listeners[event]=fn}
 trigger(type,value){if(value!==undefined)this.value=value;if(this.listeners[type])return this.listeners[type]({target:this,clientX:200,clientY:170})}
 setAttribute(k,v){this.attributes[k]=v}
 appendChild(c){this._children.push(c)}replaceChildren(...items){this._children.splice(0,this._children.length,...items)}
 click(){if(!this.disabled)return this.trigger('click')}
 getBoundingClientRect(){return {left:0,top:0,width:this.clientWidth,height:600}}
}
const context2d={};for(const fn of ['clearRect','beginPath','roundRect','fill','stroke','moveTo','lineTo','setLineDash','save','restore','arc','fillRect','fillText','setTransform'])context2d[fn]=()=>{};
const ids=['mapLoading','warehouseTitle','warehouseCanvas','presetSelect','scenarioDescription','gridDim','taskNum','riskNum','wallNum','runBtn','runLabel','dirtyText','missionStatus','apiStatus','playGlyph','viewSelect','timeStamp','timelineInput','runComment','policyBtn','downloadBtn','resetBtn','playBtn','backBtn','forwardBtn','speedSelect','toast','baseSteps','optSteps','savingPct','savingLabel','riskReduction','riskReductionUnit','riskReductionLabel','riskBase','riskMdp','comparisonSteps','successRate','sweeps','recoveryCells','barBase','barMdp','orderPills','cellTooltip'];
const els=Object.fromEntries(ids.map(id=>[id,new FakeNode('div',id)]));
els.warehouseCanvas=new FakeNode('canvas','warehouseCanvas');els.warehouseCanvas.getContext=()=>context2d;els.warehouseCanvas.parentElement=new FakeNode('div');els.warehouseCanvas.parentElement.clientWidth=1050;
els.runComment.lastChild={textContent:''};els.speedSelect.value='150';els.presetSelect.value='standard';els.viewSelect.value='mdp';
const tools=['inspect','task','shelf','hazard','erase'].map(s=>{const el=new FakeNode('button');el.dataset.tool=s;return el});
const document={getElementById:(id)=>{assert(els[id],`missing element: ${id}`);return els[id]},querySelectorAll:(selector)=>selector==='.tool'?tools:[],createElement:(tag)=>new FakeNode(tag)};
let requests=0;
let releasePresets;
const pendingPresets = new Promise(resolve => { releasePresets = resolve; });
const sandbox={document,window:{devicePixelRatio:1,addEventListener(){}},console,JSON,Math,Number,Array,Object,Blob,URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},setTimeout:()=>0,clearTimeout:()=>{},setInterval:()=>1,clearInterval:()=>{},fetch:async url=>{
 requests++;
 if(url==='/api/presets')await pendingPresets;
 return {ok:true,json:async()=>url==='/api/presets'?{presets:fixture.presets}:fixture.analysis.standard};
}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT,'web/app.js'),'utf8'),sandbox,{filename:'web/app.js'});
(async()=>{
 // The controls must handle interaction before the presets request completes.
 assert.strictEqual(els.forwardBtn.disabled,true);
 assert.strictEqual(els.playBtn.disabled,true);
 assert.doesNotThrow(() => els.viewSelect.trigger('change','mdp'));
 assert.strictEqual(els.timeStamp.textContent,'000 / 000 STEPS');
 releasePresets();
 await new Promise(resolve=>setImmediate(resolve));
 assert.strictEqual(els.baseSteps.textContent,70);
 assert.strictEqual(els.optSteps.textContent,62);
 assert.strictEqual(els.missionStatus.textContent,'MISSION PLANNED');
 assert.strictEqual(els.warehouseTitle.textContent,'Distribution center');
 assert.strictEqual(els.mapLoading.hidden,true);
 assert.strictEqual(els.warehouseCanvas.attributes['aria-busy'],'false');
 assert.ok(Number(els.riskReduction.textContent)>0);
 assert.ok(els.warehouseCanvas.width>0);
 assert.ok(requests>=2);
 // Verify route-mode state and synchronized UI
 els.viewSelect.trigger('change','optimized');
 assert.strictEqual(els.timeStamp.textContent,'000 / 062 STEPS');
 els.forwardBtn.click();
 assert.strictEqual(els.timeStamp.textContent,'001 / 062 STEPS');
 els.playBtn.click();
 assert.strictEqual(els.playBtn.attributes['aria-pressed'],'true');
 // Toggle policy; automatically switch to MDP mode
 els.policyBtn.click();
 assert.strictEqual(els.viewSelect.value,'mdp');
 assert.strictEqual(els.policyBtn.attributes['aria-pressed'],'true');
 assert.strictEqual(els.playBtn.attributes['aria-pressed'],'false');
 // Switching away from MDP must clear the overlay's pressed state.
 els.viewSelect.trigger('change','nearest');
 assert.strictEqual(els.policyBtn.attributes['aria-pressed'],'false');
 els.policyBtn.click();
 assert.strictEqual(els.policyBtn.attributes['aria-pressed'],'true');
 // An empty tile does not change the mission when erased.
 tools[4].click();
 els.warehouseCanvas.listeners.click({clientX:250,clientY:80});
 assert.strictEqual(els.missionStatus.textContent,'MISSION PLANNED');
 assert.strictEqual(els.optSteps.textContent,62);
 // Exercise map editor, which must invalidate stale model data
 tools[3].click();
 assert.strictEqual(tools[3].attributes['aria-pressed'],'true');
 assert.strictEqual(tools[0].attributes['aria-pressed'],'false');
 els.warehouseCanvas.listeners.click({clientX:250,clientY:80});
 assert.strictEqual(els.missionStatus.textContent,'REPLAN REQUIRED');
 assert.strictEqual(els.baseSteps.textContent,'—');
 assert.strictEqual(els.policyBtn.attributes['aria-pressed'],'false');
 // Old /api/analyze responses must not overwrite a newer selected scenario.
 let pending=[];
 sandbox.fetch=(url,opts)=>new Promise(resolve=>pending.push(resolve));
 els.presetSelect.trigger('change','disruption');
 els.presetSelect.trigger('change','narrow');
 assert.strictEqual(pending.length,2,'Selecting another scenario during computation must submit a new request');
 assert.strictEqual(els.mapLoading.hidden,false);
 assert.strictEqual(els.warehouseCanvas.attributes['aria-busy'],'true');
 pending[1]({ok:true,json:async()=>fixture.analysis.narrow});
 await new Promise(resolve=>setImmediate(resolve));
 assert.strictEqual(els.baseSteps.textContent,60);
 assert.strictEqual(els.warehouseTitle.textContent,'Narrow aisles');
 assert.strictEqual(els.mapLoading.hidden,true);
 pending[0]({ok:true,json:async()=>fixture.analysis.disruption});
 await new Promise(resolve=>setImmediate(resolve));
 assert.strictEqual(els.baseSteps.textContent,60,'Stale response must be ignored');
 assert.strictEqual(els.missionStatus.textContent,'MISSION PLANNED');
 assert.strictEqual(els.runBtn.disabled,false);
 // Baseline has no observed hazards: percentage reduction is undefined if MDP has entries.
 const noBaselineRisk=JSON.parse(JSON.stringify(fixture.analysis.narrow));
 noBaselineRisk.mdp.shortest_controller.mean_hazard_entries=0;
 noBaselineRisk.mdp.risk_aware_controller.mean_hazard_entries=2;
 let completeAnalysis;
 sandbox.fetch=()=>new Promise(resolve=>{completeAnalysis=resolve;});
 const newAnalysis=els.runBtn.trigger('click');
 assert.strictEqual(els.playBtn.disabled,true);
 assert.strictEqual(els.downloadBtn.disabled,true);
 completeAnalysis({ok:true,json:async()=>noBaselineRisk});
 await newAnalysis;
 assert.strictEqual(els.playBtn.disabled,false);
 assert.strictEqual(els.riskReduction.textContent,'N/A');
 assert.strictEqual(els.riskReductionUnit.textContent,'');
 assert.ok(els.riskReductionLabel.textContent.includes('undefined'));
 // A failed server replan must not leave an apparently active stale policy overlay.
 els.policyBtn.click();
 assert.strictEqual(els.policyBtn.attributes['aria-pressed'],'true');
 sandbox.fetch=async()=>({ok:false,json:async()=>({error:'Example invalid mission'})});
 await els.runBtn.trigger('click');
 assert.strictEqual(els.missionStatus.textContent,'PLAN FAILED');
 assert.strictEqual(els.policyBtn.attributes['aria-pressed'],'false');
 assert.strictEqual(els.runBtn.disabled,false);
 console.log('Frontend QA OK: delayed startup, edit, playback states, policy transitions, fast scenario switching, stale-request suppression and metric edge cases.');
})().catch(e=>{console.error(e);process.exitCode=1});
