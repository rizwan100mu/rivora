const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('.tooling/rizora-2.0.5/rizora_workforce/mobile/assets/erpnext_form_bridge.js','utf8');
async function run({mapped=false, user='worker', actual='worker',values={},amendedFrom=null}={}) {
 const docs=[];const calls=[];const errors=[];let defaults=0;
 const fields={ 'Sales Invoice':{company:{fieldtype:'Link'},items:{fieldtype:'Table'},customer:{fieldtype:'Link'}},'Sales Invoice Item':{sales_order:{fieldtype:'Link'},so_detail:{fieldtype:'Data'},item_code:{fieldtype:'Link'},qty:{fieldtype:'Float'}}};
 const frappe={boot:{},session:{user:actual},meta:{get_docfield:(dt,key)=>fields[dt]?.[key]},
   model:{table_fields:['Table'],with_doctype:async()=>{},get_new_doc:(doctype)=>{defaults++;const doc={doctype,name:'new-1',docstatus:0,company:'ERP-SITE-DEFAULT',items:[{doctype:'Sales Invoice Item'}]};docs.push(doc);return doc;},
     clear_table:(doc,key)=>{doc[key]=[];},add_child:(doc,key)=>{const child={doctype:'Sales Invoice Item',name:'new-child',parent:doc.name};doc[key].push(child);return child;}},
   msgprint:(message)=>errors.push(message),set_route:(...args)=>calls.push(args)};
 const context={window:{__rizoraFormConfig:{doctype:'Sales Invoice',mapped,user,values,amendedFrom},setTimeout},frappe};context.window.frappe=frappe;
 vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));
 vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));
 return {doc:docs[0],calls,errors,defaults};
}
(async()=>{
 let r=await run();assert.equal(r.doc.company,'ERP-SITE-DEFAULT');assert.equal(r.defaults,1);assert.equal(r.calls.length,1);
 r=await run({mapped:true,values:{company:'B',docstatus:1,ignore_permissions:true,__mobile_test:'x',items:[{item_code:'ITEM',sales_order:'SO-1',so_detail:'SO-ROW',name:'bad',parent:'bad',qty:3}]}});
 assert.equal(r.doc.company,'B');assert.equal(r.doc.docstatus,0);assert.equal(r.doc.ignore_permissions,undefined);assert.equal(r.doc.__mobile_test,undefined);
 assert.equal(r.doc.items.length,1);assert.equal(r.doc.items[0].so_detail,'SO-ROW');assert.equal(r.doc.items[0].parent,'new-1');assert.equal(r.doc.items[0].qty,3);assert.equal(r.doc.__onload.load_after_mapping,true);
 r=await run({amendedFrom:'SINV-1'});assert.equal(r.doc.amended_from,'SINV-1');
 r=await run({actual:'another-user'});assert.equal(r.doc,undefined);assert.equal(r.errors.length,1);
 console.log('4 Frappe form bridge scenarios passed (defaults, mapped links, amendment, identity).');
})().catch(e=>{console.error(e);process.exitCode=1;});
