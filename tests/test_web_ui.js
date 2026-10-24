// Regression: initialize the shipped HTML and exercise all upload event bindings.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('heat_pump_ready/web/index.html','utf8');
class Element {
 constructor(){this.children=[];this.events={};this.dataset={};this.value='';this.files=[];this.classList={toggle(){},remove(){}};}
 append(...items){this.children.push(...items)}
 replaceChildren(...items){this.children=items}
 addEventListener(name,handler){this.events[name]=handler}
 click(){this.clicked=true;return this.events.click?.({target:this})}
 setAttribute(){}
}
const nodes=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(match=>['#'+match[1],new Element()]));
const fields=Object.fromEntries([...html.matchAll(/\bname="([^"]+)"/g)].map(match=>[match[1],new Element()]));
nodes['#assessment-form'].elements={namedItem:name=>fields[name]};fields.energy_carrier.value='gas';
const document={querySelector(selector){if(!nodes[selector])throw Error('Missing HTML element: '+selector);return nodes[selector]},querySelectorAll(){return []},createElement(){return new Element()}};
const context={document,console,fetch:async(url)=>({ok:true,json:async()=>url==='/api/pipe-preview'?{pipe_system:'two-pipe'}:url==='/api/bill-preview'?{annual_consumption:13666,consumption_unit:'kwh'}:({runner:'api',cases:[{id:'B-01'}],modules:[{key:'heat_load'}]})}),FileReader:class{readAsDataURL(){this.result='data:image/png;base64,TEST';this.onload()}},setTimeout};
vm.createContext(context);vm.runInContext(fs.readFileSync('heat_pump_ready/web/app.js','utf8'),context);
(async()=>{
 await new Promise(resolve=>setImmediate(resolve));
 assert(!nodes['#error'].textContent,'Initialization failed');
 assert.equal((html.match(/class="wizard-step"/g)||[]).length,4);assert(!html.includes('data-step="4"'));assert(!html.includes('data-goto="4"'));
 assert(nodes['#chat-status'].textContent.includes('verbunden'));
 await nodes['#upload-bill'].click();assert(nodes['#bill-files'].clicked);
 await nodes['#upload-connections'].click();assert(nodes['#connection-files'].clicked);
 const file={name:'demo.png',type:'image/png',size:10};
 nodes['#bill-files'].files=[file];await nodes['#bill-files'].events.change({target:nodes['#bill-files']});
 assert.equal(vm.runInContext('attachments[0].category',context),'bill');assert.equal(nodes['#bill-file-list'].children.length,1);assert.equal(fields.annual_consumption.value,'13666');assert.equal(fields.consumption_unit.value,'kwh');
 nodes['#connection-files'].files=[file];await nodes['#connection-files'].events.change({target:nodes['#connection-files']});
 assert.equal(vm.runInContext('connectionImages[0].category',context),'pipes');assert.equal(nodes['#connection-file-list'].children.length,1);assert.equal(fields.pipe_system.value,'two-pipe');assert(nodes['#pipe-upload-status'].textContent.includes('Zweirohrsystem'));
 nodes['#connection-file-list'].children[0].children[0].click();assert.equal(vm.runInContext('connectionImages.length',context),0);assert.equal(fields.pipe_system.value,'unknown');
 nodes['#bill-files'].files=[{...file,size:5*1024*1024}];await nodes['#bill-files'].events.change({target:nodes['#bill-files']});assert(nodes['#error'].textContent.includes('4 MiB'));assert.equal(vm.runInContext('uploadsPending',context),0);
 console.log('Passed: HTML initialization, bill/connection uploads, removal and size validation.');
})().catch(error=>{console.error(error);process.exitCode=1});
