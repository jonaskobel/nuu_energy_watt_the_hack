/* Interface only. All numerical calculations and decisions remain in the existing Python pipeline. */
const labels={annual_consumption:'Jahresverbrauch',useful_heat:'Nutzwärme',hot_water_demand:'Warmwasserbedarf',space_heating_demand:'Raumwärmebedarf',heat_load_consumption:'Heizlast aus Verbrauch',heat_load_area:'Heizlast aus Fläche',heat_load:'Heizlast (Schätzung)',specific_heat_load:'Spezifische Heizlast',radiator_type:'Heizkörpertyp',pipe_system:'Rohrsystem',annual_performance_factor:'Jahresarbeitszahl',current_energy_cost:'Energiekosten heute',heat_pump_energy_cost:'Energiekosten Wärmepumpe',annual_savings:'Jährliche Ersparnis',net_investment:'Nettoinvestition',payback_period:'Einfache Amortisation',horizon:'Betrachtungszeitraum'};
const statuses={missing_input:'Angaben fehlen',disabled:'Deaktiviert',blocked:'Vorberechnung fehlt',failed:'Technischer Fehler'};
const $=selector=>document.querySelector(selector);
const form=$('#assessment-form');
let config,latestResult,attachments=[],connectionImages=[],uploadsPending=0,step=0,farthest=0,chatHistory=[],chatBusy=false,chatController=null;
/** Create text-safe nodes; user and model text is never HTML. */
function el(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
function formatValue(value){if(Array.isArray(value))return value.map(formatValue).join(' – ');if(typeof value==='number')return new Intl.NumberFormat('de-DE',{maximumFractionDigits:1}).format(value);return {'two-pipe':'Zweirohr','single-pipe':'Einrohr',no_finite_payback:'Keine endliche Amortisation'}[value]||value;}
/** Keep visual choices and existing named select fields in sync. */
function syncChoices(){document.querySelectorAll('[data-field]').forEach(button=>{const value=form.elements.namedItem(button.dataset.field).value;const selected=button.dataset.value===value||(button.dataset.value==='gas'&&value==='lpg');button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});}
document.querySelectorAll('[data-field]').forEach(button=>button.addEventListener('click',()=>{form.elements.namedItem(button.dataset.field).value=button.dataset.value;syncChoices();}));
form.addEventListener('change',syncChoices);
/** Show one question group without discarding values from the others. */
function showStep(index,focus=true){step=index;farthest=Math.max(farthest,index);document.querySelectorAll('.wizard-step').forEach((section,i)=>section.hidden=i!==index);document.querySelectorAll('[data-goto]').forEach((button,i)=>{button.disabled=i>farthest;button.classList.toggle('complete',i<index);if(i===index)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');});$('#progress-fill').style.width=((index+1)*20)+'%';$('#step-counter').textContent=`Schritt ${index+1} von 5`;$('#back').hidden=index===0;$('#next').hidden=index===4;$('#submit').hidden=index!==4;$('#error').textContent='';if(focus){$('#title-'+index).focus({preventScroll:true});if(window.scrollY>150)$('.wizard-shell').scrollIntoView({behavior:'smooth',block:'start'});}}
function validStep(index){const section=document.querySelector(`[data-step="${index}"]`);for(const field of section.querySelectorAll('input,select,textarea')){if(!field.checkValidity()){showStep(index);field.reportValidity();return false;}}return true;}
$('#next').addEventListener('click',()=>{if(validStep(step))showStep(Math.min(4,step+1));});
$('#back').addEventListener('click',()=>showStep(Math.max(0,step-1)));
document.querySelectorAll('[data-goto]').forEach(button=>button.addEventListener('click',()=>{const target=Number(button.dataset.goto);if(target<step||validStep(step))showStep(target);}));
form.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.tagName==='INPUT'&&event.target.type!=='file'&&step<4){event.preventDefault();$('#next').click();}});
/** Expose actual model availability, including external data transmission. */
function updateModelStatus(){const mode=config?.runner;$('#chat-status').textContent=mode==='api'?'Mit deinem konfigurierten Modell verbunden':mode==='mlx'?'Lokales Modell verbunden':'Noch kein LLM aktiviert';$('#chat-privacy').textContent=mode==='api'?'Frage, Gespräch und Ergebnis gehen an den konfigurierten Modellanbieter.':mode==='mlx'?'Frage und Ergebnis werden lokal verarbeitet.':'Für Antworten muss ein LLM verbunden sein.';$('#runner-info').textContent=mode==='api'?'API-Modus: Zugeordnete Bilder werden beim Berechnen an den konfigurierten Modellanbieter gesendet.':mode==='mlx'?'Lokales Modell: Bildauswertung auf diesem Rechner.':'Offline-Modus: Bild- und Rechnungserkennung deaktiviert. Angaben bitte manuell eingeben.';$('#connection-runner-info').textContent=$('#runner-info').textContent;$('#bill-runner-info').textContent=$('#runner-info').textContent;}
async function init(){try{const response=await fetch('/api/config');if(!response.ok)throw Error('Konfiguration nicht erreichbar. Bitte den lokalen Server prüfen.');config=await response.json();for(const item of config.cases){const option=el('option',`${item.id} · ${item.floor_area_m2} m²`);option.value=item.id;$('#example').append(option);}for(const module of config.modules){const label=el('label',undefined,'module');const check=document.createElement('input');check.type='checkbox';check.checked=true;check.defaultChecked=true;check.dataset.key=module.key;label.append(check,el('span',labels[module.key]||module.key));$('#module-list').append(label);}updateModelStatus();}catch(error){$('#error').textContent=error.message;}syncChoices();}
function resetChat(){if(chatController)chatController.abort();chatController=null;chatBusy=false;chatHistory=[];$('#chat-send').disabled=false;$('#chat-messages').replaceChildren(el('div','Hallo! Was möchtest du zu deiner Ersteinschätzung wissen?','chat-message assistant'));$('#chat-question').value='';$('#chat-error').textContent='';}
$('#example').addEventListener('change',event=>{if(!config)return;form.reset();attachments=[];connectionImages=[];renderFiles();latestResult=null;resetChat();$('#result-view').hidden=true;$('#check-view').hidden=false;const sample=event.target.value==='synthetic'?config.synthetic:config.cases.find(item=>item.id===event.target.value);if(sample){for(const [key,value]of Object.entries(sample)){const input=form.elements.namedItem(key);if(input)input.value=value===null?'':String(value);}}syncChoices();farthest=0;showStep(0,false);});
/** Read uploads into the selected input collection, preserving existing categories. */
async function addFiles(event, connections=false, categoryOverride=null){
 const selected=[...event.target.files];
 const category=connections?'pipes':categoryOverride||$('#file-category').value;
 const target=connections?connectionImages:attachments;
 $('#error').textContent='';uploadsPending++;
 try{
  const pending=[];
  for(const file of selected){
   if(file.size>4*1024*1024)throw Error('Datei größer als 4 MiB: '+file.name);
   const types=connections?['image/jpeg','image/png']:['image/jpeg','image/png','application/pdf'];
   if(!types.includes(file.type))throw Error(connections?'Bitte JPG oder PNG verwenden.':'Bitte JPG, PNG oder PDF verwenden.');
   const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Datei konnte nicht gelesen werden.'));reader.readAsDataURL(file);});
   pending.push({name:file.name,media_type:file.type,category,data});
  }
  if(target!==(connections?connectionImages:attachments))return;
  if(attachments.length+connectionImages.length+pending.length>6)throw Error('Maximal sechs Dateien erlaubt.');
  target.push(...pending);renderFiles();
 }catch(error){$('#error').textContent=error.message;}
 finally{uploadsPending--;event.target.value='';}
}
$('#files').addEventListener('change',event=>addFiles(event));
$('#bill-files').addEventListener('change',event=>addFiles(event,false,'bill'));
$('#upload-bill').addEventListener('click',()=>$('#bill-files').click());
$('#connection-files').addEventListener('change',event=>addFiles(event,true));
$('#upload-connections').addEventListener('click',()=>$('#connection-files').click());
/** Display removable uploads in their respective form sections. */
function renderFiles(){
 for(const [selector,files] of [['#file-list',attachments],['#connection-file-list',connectionImages],['#bill-file-list',attachments]]){
  const list=$(selector);list.replaceChildren();
  files.forEach((file,index)=>{if(selector==='#bill-file-list'&&file.category!=='bill')return;const row=el('li',file.name+' · '+(selector==='#connection-file-list'?'Heizungsanschluss':file.category)+' ');const remove=el('button','Entfernen');remove.type='button';remove.addEventListener('click',()=>{files.splice(index,1);renderFiles();});row.append(remove);list.append(row);});
 }
}
/** Submit input and connection photos to the existing assessment route. */
form.addEventListener('submit',async event=>{event.preventDefault();if(step<4){$('#next').click();return;}if(uploadsPending){$('#error').textContent='Bitte warten, bis die Bilder eingelesen sind.';return;}for(let i=0;i<5;i++)if(!validStep(i))return;const button=$('#submit');$('#error').textContent='';button.disabled=true;button.textContent='Wird berechnet …';try{const input=Object.fromEntries(new FormData(form));input.hot_water_via_heating=input.hot_water_via_heating===''?null:input.hot_water_via_heating==='true';input.attachments=attachments;input.heating_connection_images=connectionImages;const disabled_modules=[...document.querySelectorAll('[data-key]')].filter(item=>!item.checked).map(item=>item.dataset.key);const response=await fetch('/api/assessments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input,disabled_modules})});const result=await response.json();if(!response.ok)throw Error(result.error||'Berechnung fehlgeschlagen.');latestResult=result;resetChat();renderResults(result);$('#check-view').hidden=true;$('#result-view').hidden=false;window.scrollTo({top:0,behavior:'smooth'});$('#result-title').focus({preventScroll:true});}catch(error){$('#error').textContent=error.message;}finally{button.disabled=false;button.replaceChildren(document.createTextNode('Meine Einschätzung '),el('span','↗'));}});
$('#edit-inputs').addEventListener('click',()=>{resetChat();$('#result-view').hidden=true;$('#check-view').hidden=false;showStep(step);window.scrollTo({top:0,behavior:'smooth'});});
/** Make the billed consumption and any extraction limitations visible. */
function renderBillAnalysis(metric){
 if(!metric)return null;
 const section=el('section',undefined,'result-section pipe-decision');section.dataset.metric='bill_analysis';
 const model=/gemma/i.test(metric.source||'');
 section.append(el('h3',model?'Jahresabrechnung · Auswertung von Gemma 4':'Jahresabrechnung · Verbrauchsdaten'));
 section.append(el('p',metric.status==='available'?formatValue(metric.value)+' kWh/Jahr':statuses[metric.status]||'Verbrauch nicht erkennbar','pipe-decision-value'));
 if(metric.status==='available')section.append(el('p',metric.uncertainty?'Aus der Rechnung erkannt. Die verfügbaren Kennzahlen wurden mit diesem Verbrauch neu berechnet.':'Dein bereits eingegebener Jahresverbrauch wurde verwendet.','hint'));
 for(const text of [...metric.assumptions,...metric.evidence,metric.uncertainty].filter(Boolean))section.append(el('p',text,'hint'));
 section.append(el('p','Energiekosten und Ersparnis verwenden die Challenge-Tarife, nicht Abschläge, Guthaben oder den Gesamtrechnungsbetrag.','hint'));
 section.append(el('p','Die jährliche Ersparnis benötigt zusätzlich eine Jahresarbeitszahl aus Heizflächenart und Vorlauftemperatur. Investitionskosten und Förderung lassen sich aus einer Energieabrechnung nicht ableiten.','hint'));
 return section;
}
/** Show each image classification with its model source and visual evidence. */
function renderImageDecision(metric,key){
 if(!metric)return null;
 const pipes=key==='pipe_system';
 const manual=pipes&&metric.status==='available'&&metric.evidence.includes('Explizite Nutzerangabe.');
 const gemma=/gemma/i.test(metric.source||'');
 const title=pipes?'Rohrsystem':'Heizkörpertyp';
 const section=el('section',undefined,'result-section pipe-decision');
 section.dataset.metric=key;
 section.append(el('h3',manual?'Dein Rohrsystem':title+(gemma?' · Entscheidung von Gemma 4':' · Bildauswertung')));
 const values=pipes?{'single-pipe':'Einrohrsystem','two-pipe':'Zweirohrsystem'}:{'11':'Typ 11','22':'Typ 22','33':'Typ 33'};
 const classification=metric.status==='available'?values[metric.value]:null;
 const outcome=classification||{disabled:'Bildauswertung deaktiviert',failed:'Bildauswertung fehlgeschlagen',missing_input:'Keine eindeutige Entscheidung',blocked:'Bildauswertung nicht verfügbar'}[metric.status]||'Keine eindeutige Entscheidung';
 section.append(el('p',outcome,'pipe-decision-value'));
 if(manual)section.append(el('p','Du hast das Rohrsystem selbst angegeben.','hint'));
 else if(classification)section.append(el('p',pipes?'Die Mehrheit der auswertbaren Bilder spricht für dieses Rohrsystem.':'Die Erkennung bezieht sich auf den abgebildeten Heizkörper.','hint'));
 if(!pipes&&classification){
  const descriptions={'11':'Eine Heizplatte und eine Konvektorlage.','22':'Zwei Heizplatten und zwei Konvektorlagen.','33':'Drei Heizplatten und drei Konvektorlagen.'};
  section.append(el('p',descriptions[metric.value],'hint'));
 }
 for(const text of metric.evidence.filter(text=>!pipes||text.startsWith('Abstimmung:')))section.append(el('p',text,'hint'));
 const details=el('details');details.append(el('summary',pipes?'Bildentscheidungen und Grundlage anzeigen':'Begründung und Grundlage anzeigen'));
 for(const text of [...metric.evidence,metric.uncertainty,metric.source?'Quelle: '+metric.source:null].filter(Boolean))details.append(el('p',text,'hint'));
 section.append(details);
 return section;
}
/** Present the separate model recommendation after both image classifications. */
function renderInvestmentRecommendation(recommendation){
 if(!recommendation)return null;
 const section=el('section',undefined,'result-section pipe-decision investment-recommendation');
 section.dataset.metric='investment_recommendation';
 const gemma=/gemma/i.test(recommendation.source||'');
 section.append(el('h3',gemma?'Lohnt sich die Wärmepumpe? · Empfehlung von Gemma 4':'Lohnt sich die Wärmepumpe? · KI-Empfehlung'));
 if(recommendation.status!=='available'){
  section.append(el('p',recommendation.status==='disabled'?'Empfehlung deaktiviert':'Empfehlung konnte nicht erstellt werden','pipe-decision-value'));
  section.append(el('p',recommendation.error||'Bitte die Berechnung erneut ausführen.','hint'));
  return section;
 }
 const verdicts={worthwhile:'Voraussichtlich lohnenswert',not_worthwhile:'Unter diesen Annahmen nicht lohnenswert',undetermined:'Noch nicht abschließend beurteilbar'};
 section.append(el('p',verdicts[recommendation.verdict]||verdicts.undetermined,'pipe-decision-value'),el('p',recommendation.summary));
 for(const [title,text] of [['Technische Eignung',recommendation.technical_assessment],['Wirtschaftlichkeit',recommendation.economic_assessment]]){
  section.append(el('h4',title),el('p',text));
 }
 for(const [title,items] of [['Unsicherheiten und fehlende Angaben',recommendation.uncertainties],['Deine nächsten Schritte',recommendation.next_steps]]){
  if(!items.length)continue;
  section.append(el('h4',title));const list=el(title==='Deine nächsten Schritte'?'ol':'ul');
  items.forEach(text=>list.append(el('li',text)));section.append(list);
 }
 section.append(el('h4','Fazit'),el('p',recommendation.conclusion),el('p','Ersteinschätzung auf Basis der vereinfachten Challenge-Annahmen.','hint'));
 if(recommendation.source)section.append(el('p','Quelle: '+recommendation.source,'hint'));
 return section;
}
/** Render backend values verbatim, retaining every assumption and decision reason. */
function renderResults(result){const panel=$('#results');panel.replaceChildren();const decision=result.decision;const card=el('section',undefined,'decision '+decision.verdict);card.append(el('div','DEINE ERSTE EINSCHÄTZUNG','eyebrow'),el('h2',{worthwhile:'Dein Zuhause hat Potenzial.',not_worthwhile:'Ein genauer Blick lohnt sich.',undetermined:'Ein paar Fragen bleiben offen.'}[decision.verdict]||'Deine Ersteinschätzung.'));card.append(el('p',decision.summary),el('span','Technik: '+{green:'voraussichtlich geeignet',yellow:'Prüfbedarf',red:'Hindernis oder zu wenig Belege'}[decision.readiness],'tag '+decision.readiness),el('span','Vereinfachtes Demo-Entscheidungsmodell','tag'));panel.append(card);
 const highlights=el('section',undefined,'metric-highlights');highlights.setAttribute('aria-label','Wichtige Kennzahlen');for(const key of ['heat_load','annual_performance_factor','annual_savings','payback_period']){const metric=result.metrics[key];if(!metric)continue;const tile=el('div',undefined,'highlight');tile.append(el('span',labels[key]),el('strong',metric.status==='available'?formatValue(metric.value)+(metric.unit?' '+metric.unit:''):'Noch offen'),el('small',metric.status==='available'?'Grundlagen in den Kennzahlen':statuses[metric.status]||'Angaben prüfen'));highlights.append(tile);}panel.append(highlights);
 const criterionLabels={heat_load:'Heizlast',temperature:'Temperaturniveau',hydraulics:'Hydraulik'};const criterionMarks={met:'✓',open:'?',obstacle:'✗'};const criteria=(decision.criteria||[]).map(c=>criterionMarks[c.state]+' '+(criterionLabels[c.key]||c.key)+(c.strength==='indicator'?' (Indiz)':'')+': '+c.reason);for(const [title,items]of [['Technische Kriterien',criteria],['Für eine sichere Aussage fehlt noch',decision.readiness_gaps||[]],['Warum diese Einschätzung?',decision.reasons],['Bitte zuerst klären',decision.validation_issues],['Diese Angaben fehlen noch',decision.missing_information.map(key=>labels[key]||key)]]){if(!items.length)continue;const section=el('section',undefined,'result-section');section.append(el('h3',title));const list=el('ul');items.forEach(item=>list.append(el('li',item)));section.append(list);panel.append(section);}
 const metrics=el('details',undefined,'result-section metrics-detail');metrics.append(el('summary','Alle Kennzahlen & Rechengrundlagen'));for(const [key,metric]of Object.entries(result.metrics)){const row=el('div',undefined,'metric');const top=el('div',undefined,'metric-top');top.append(el('span',labels[key]||key),el('strong',metric.status==='available'?formatValue(metric.value)+(metric.unit?' '+metric.unit:''):statuses[metric.status]||metric.status));row.append(top);const details=el('details');details.append(el('summary',(metric.demonstration?'Demoannahme · ':'')+'Grundlage anzeigen'));for(const part of [...metric.assumptions,...metric.evidence,metric.uncertainty,metric.source?'Quelle: '+metric.source:null].filter(Boolean))details.append(el('p',labels[part]||part));row.append(details);metrics.append(row);}panel.append(metrics);
 const checks=el('section',undefined,'result-section');checks.append(el('h3','Mit dem Fachbetrieb prüfen'));const list=el('ul');decision.technician_checks.forEach(text=>list.append(el('li',text)));checks.append(list,el('p','Die Amortisation berücksichtigt keine Zinsen, Wartung, Grundpreise, Energiepreisänderungen oder Ersatzinvestitionen.','hint'));panel.append(checks);const billAnalysis=renderBillAnalysis(result.bill_analysis);if(billAnalysis)panel.append(billAnalysis);for(const key of ['pipe_system','radiator_type']){const imageDecision=renderImageDecision(result.metrics[key],key);if(imageDecision)panel.append(imageDecision);}const recommendation=renderInvestmentRecommendation(result.recommendation);if(recommendation)panel.append(recommendation);const download=el('button','Ergebnis als JSON herunterladen ↓','download');download.type='button';download.addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(latestResult,null,2)],{type:'application/json'}));const anchor=el('a');anchor.href=url;anchor.download='waermeweise-ergebnis.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});panel.append(download);}
/** Chat only explains existing results; it cannot update form fields or metrics. */
async function askAssistant(){if(chatBusy||!latestResult)return;const field=$('#chat-question');const question=field.value.trim();if(!question){field.focus();return;}$('#chat-error').textContent='';if(!config||config.runner==='disabled'){$('#chat-error').textContent='Der Chat ist vorbereitet, aber noch kein LLM aktiviert. Starte die Anwendung mit einem konfigurierten API- oder lokalen Modell.';return;}chatBusy=true;$('#chat-send').disabled=true;const controller=new AbortController();chatController=controller;const userNode=el('div',question,'chat-message user');const pending=el('div','Dein Assistent denkt nach …','chat-message assistant pending');$('#chat-messages').append(userNode,pending);field.value='';pending.scrollIntoView({behavior:'smooth',block:'nearest'});try{const context={decision:latestResult.decision,recommendation:latestResult.recommendation,metrics:Object.fromEntries(Object.entries(latestResult.metrics).map(([key,m])=>[key,{value:m.value,unit:m.unit,status:m.status,assumptions:m.assumptions,uncertainty:m.uncertainty}]))};const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({question,history:chatHistory.slice(-8),context})});const data=await response.json();if(!response.ok)throw Error(data.error||'Der Assistent ist gerade nicht erreichbar.');if(typeof data.answer!=='string'||!data.answer.trim())throw Error('Das Modell hat keine Antwort geliefert.');pending.textContent=data.answer;pending.classList.remove('pending');chatHistory.push({role:'user',text:question},{role:'assistant',text:data.answer});pending.scrollIntoView({behavior:'smooth',block:'nearest'});}catch(error){pending.remove();if(error.name!=='AbortError'){$('#chat-error').textContent=error.message;field.value=question;userNode.remove();}}finally{if(chatController===controller){chatController=null;chatBusy=false;$('#chat-send').disabled=false;}}}
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();askAssistant();});
$('#chat-question').addEventListener('keydown',event=>{if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();askAssistant();}});
document.querySelectorAll('[data-question]').forEach(button=>button.addEventListener('click',()=>{$('#chat-question').value=button.dataset.question;$('#chat-question').focus();}));
init();

$('#offer-form').addEventListener('submit',async event=>{event.preventDefault();if(offerBusy)return;const button=$('#offer-submit');$('#offer-error').textContent='';$('#offer-status').textContent='';offerBusy=true;button.disabled=true;try{const contact=Object.fromEntries(new FormData(event.currentTarget));const response=await fetch('/api/offer-requests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...contact,assessment_token:assessmentToken})});const result=await response.json();if(!response.ok)throw Error(result.error||'Anfrage konnte nicht gespeichert werden.');$('#offer-status').textContent=result.message;}catch(error){$('#offer-error').textContent=error.message;button.disabled=false;}finally{offerBusy=false;}});
