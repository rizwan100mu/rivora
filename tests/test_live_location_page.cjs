const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../rizora_workforce/rizora_workforce/page/employee_live_location/employee_live_location.js'),'utf8');
class Element {
  constructor(){this.children=[];this.style={};this.value='';this.clientWidth=800;this.clientHeight=500;this.classes=new Set();this.classList={toggle:(key,yes)=>yes?this.classes.add(key):this.classes.delete(key)};}
  appendChild(child){this.children.push(child);child.parent=this;return child;}
  append(...items){for(const item of items)this.appendChild(item);}
  replaceChildren(...items){this.children=[];this.append(...items);}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}
  querySelector(selector){return this.registry[selector];}
  setPointerCapture(){}
}
function setup(){
  const elements={};for(const key of ['.map','.search','.state','.tiles','.markers','.empty','.rows','.zoom-in','.zoom-out','.fit'])elements[key]=new Element();
  const document={hidden:false,handlers:{},createElement:()=>{const element=new Element();element.registry=elements;return element;},addEventListener:(event,fn)=>document.handlers[event]=fn};
  const route=['employee-live-location'],requests=[],timers=new Map(),wrapper={},body=new Element();
  let reply={employees:[{employee:'EMP-1',employee_name:'Worker',company:'A',latitude:24,longitude:46,status:'recent',age_seconds:0,captured_at:'2026-11-08 10:00:00'}]},failure;
  const frappe={pages:{'employee-live-location':{}},session:{user:'Administrator'},get_route:()=>route,router:{on:(event,fn)=>frappe.changed=fn},ui:{make_app_page:()=>({main:{get:()=>body}})},call:async options=>{requests.push(options);if(failure)throw failure;return {message:reply};}};
  vm.runInNewContext(source,{frappe,document,__:text=>text,ResizeObserver:class{observe(){}},setInterval:(fn,delay)=>{assert.equal(delay,5000);const key=timers.size+1;timers.set(key,fn);return key;},clearInterval:key=>timers.delete(key),$:()=>({on(){return this;}})});
  frappe.pages['employee-live-location'].on_page_load(wrapper);
  return {elements,frappe,document,route,requests,timers,wrapper,setReply:value=>reply=value,setFailure:value=>failure=value};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('admin page loads automatically with a read-only scoped API and stops when hidden',async()=>{
  const app=setup();await flush();
  assert.equal(app.requests.length,1);assert.equal(app.requests[0].method,'rizora_workforce.live_location.latest');assert.equal(app.requests[0].type,'GET');
  assert.equal(app.elements['.markers'].children.length,1);
  await [...app.timers.values()][0]();assert.equal(app.requests.length,2);
  app.document.hidden=true;app.document.handlers.visibilitychange();assert.equal(app.timers.size,0);
  await app.wrapper.rizora_live_map.refresh();assert.equal(app.requests.length,2);
  app.document.hidden=false;app.document.handlers.visibilitychange();await flush();assert.equal(app.requests.length,3);
  app.route[0]='List';app.frappe.changed();assert.equal(app.timers.size,0);
});
test('permission denial clears previously visible employee positions',async()=>{
  const app=setup();await flush();app.setFailure({status:403});
  await app.wrapper.rizora_live_map.refresh();
  assert.equal(app.elements['.markers'].children.length,0);assert.equal(app.elements['.rows'].children.length,0);
  assert.match(app.elements['.state'].textContent,/access denied/);
});
test('stale markers are grey and employee names are inserted as text',async()=>{
  const app=setup();await flush();
  const label='<img src=x onerror=alert(1)>';
  app.setReply({employees:[{employee:'EMP-2',employee_name:label,company:'A',latitude:24,longitude:46,status:'recent',age_seconds:181}]});
  await app.wrapper.rizora_live_map.refresh();
  const pin=app.elements['.markers'].children[0];assert.equal(pin.textContent,label);assert.equal(pin.classes.has('old'),true);assert.equal(pin.children.length,0);
});
test('a response arriving after leaving the page cannot replace its map',async()=>{
  const app=setup();await flush();let resolve;
  app.frappe.call=()=>new Promise(done=>resolve=done);
  const pending=app.wrapper.rizora_live_map.refresh();
  app.route[0]='List';app.frappe.changed();
  resolve({message:{employees:[]}});await pending;
  assert.equal(app.elements['.markers'].children.length,1);
});
