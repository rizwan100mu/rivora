/* Near-live admin map. All employee visibility is enforced by the server API. */
frappe.pages['employee-live-location'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent:wrapper, title:__('Employee Live Location'), single_column:true});
  const root = document.createElement('div');
  root.className = 'rivora-live-location';
  root.innerHTML = `<style>
    .rivora-live-location .toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
    .rivora-live-location .search{max-width:340px;flex:1;min-width:160px}
    .rivora-live-location .map{position:relative;overflow:hidden;height:60vh;min-height:320px;max-height:780px;background:#dce6e1;touch-action:none;border:1px solid var(--border-color);border-radius:10px}
    .rivora-live-location .tiles,.rivora-live-location .markers{position:absolute;inset:0;pointer-events:none}
    .rivora-live-location .tile{position:absolute;width:256px;height:256px;max-width:none}
    .rivora-live-location .pin{position:absolute;transform:translate(-50%,-100%);white-space:nowrap;background:#146b60;color:white;border:2px solid white;border-radius:12px;padding:3px 7px;box-shadow:0 1px 4px #0005;font-size:12px;transition:left .7s linear,top .7s linear;pointer-events:auto}
    .rivora-live-location .pin.old{background:#66736f}
    .rivora-live-location .attribution{position:absolute;bottom:0;left:0;background:white;color:#222;font-size:11px;padding:3px 5px;z-index:2}
    .rivora-live-location .map-controls{position:absolute;top:8px;right:8px;display:flex;flex-direction:column;gap:5px;z-index:3}
    .rivora-live-location .empty{position:absolute;top:45%;width:100%;text-align:center;color:#263c35}
    .rivora-live-location .rows{max-height:300px;overflow:auto;margin-top:8px}
    .rivora-live-location .person{display:flex;gap:8px;justify-content:space-between;align-items:center;width:100%;padding:8px 12px;border:0;border-bottom:1px solid var(--border-color);background:var(--card-bg);color:var(--text-color);text-align:start}
    .rivora-live-location .person small{display:block;opacity:.75}
  </style><div class="toolbar"><input class="form-control search" aria-label="Find employee or company" placeholder="Find employee or company"><span class="state" role="status"></span></div>
  <div class="map" role="region" aria-label="Employee live map"><div class="tiles"></div><div class="markers"></div><div class="empty"></div><div class="map-controls"><button class="btn btn-default zoom-in" aria-label="Zoom in">+</button><button class="btn btn-default zoom-out" aria-label="Zoom out">−</button><button class="btn btn-default fit">Fit locations</button></div><a class="attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a></div>
  <div class="text-muted small">Near-live positions update automatically while this page is open. Grey markers are stale or stopped. Offline phones show their last received position.</div><div class="rows"></div>`;
  page.main.get(0).appendChild(root);
  const q = name => root.querySelector(name), map = q('.map');
  const state = {rows:[], busy:false, active:false, timer:null, generation:0, loaded:0, x:.5, y:.5, z:12, follow:true, focus:null, dragging:null, tileNodes:new Map(), markerNodes:new Map()};
  const project = row => {
    const latitude = Math.max(-85.05112878, Math.min(85.05112878, Number(row.latitude))) * Math.PI / 180;
    return {x:(Number(row.longitude)+180)/360, y:(1-Math.log(Math.tan(latitude)+1/Math.cos(latitude))/Math.PI)/2};
  };
  const valid = row => typeof row.latitude === 'number' && Number.isFinite(row.latitude) && Math.abs(row.latitude)<=90 && typeof row.longitude === 'number' && Number.isFinite(row.longitude) && Math.abs(row.longitude)<=180;
  const visibleRows = () => {
    const text=q('.search').value.toLowerCase().trim();
    return state.rows.filter(row => `${row.employee_name || ''} ${row.employee || ''} ${row.company || ''}`.toLowerCase().includes(text));
  };
  const rowStatus = row => row.status === 'recent' && Number(row.age_seconds || 0)+(Date.now()-state.loaded)/1000 > 180 ? 'stale' : row.status;
  function fit() {
    const all=visibleRows().filter(valid), focused=all.filter(row=>row.employee===state.focus);
    const points=(focused.length ? focused : all).map(project);
    if(!points.length) return;
    const left=Math.min(...points.map(p=>p.x)),right=Math.max(...points.map(p=>p.x));
    const top=Math.min(...points.map(p=>p.y)),bottom=Math.max(...points.map(p=>p.y));
    state.x=(left+right)/2;state.y=(top+bottom)/2;
    if(points.length===1) {state.z=Math.max(state.z,14);return;}
    const factor=Math.min(Math.max(map.clientWidth-100,1)/(256*Math.max(right-left,1e-9)), Math.max(map.clientHeight-100,1)/(256*Math.max(bottom-top,1e-9)));
    state.z=Math.max(2,Math.min(16,Math.floor(Math.log2(factor))));
  }
  function render() {
    const rows=visibleRows(), points=rows.filter(valid), n=2**state.z, scale=n*256;
    const left=state.x*scale-map.clientWidth/2,top=state.y*scale-map.clientHeight/2;
    const visibleTiles=new Set();
    q('.empty').textContent=points.length ? '' : __('No captured locations to show yet. Employees must start location sharing on their phones.');
    if(points.length) {
      for(let x=Math.floor(left/256);x<=Math.floor((left+map.clientWidth)/256);x++) {
        for(let y=Math.floor(top/256);y<=Math.floor((top+map.clientHeight)/256);y++) {
          if(y<0 || y>=n) continue;
          const key=`${state.z}:${x}:${y}`;visibleTiles.add(key);
          let image=state.tileNodes.get(key);
          if(!image) {image=document.createElement('img');image.className='tile';image.alt='';image.draggable=false;image.src=`https://tile.openstreetmap.org/${state.z}/${((x%n)+n)%n}/${y}.png`;q('.tiles').appendChild(image);state.tileNodes.set(key,image);}
          image.style.left=`${x*256-left}px`;image.style.top=`${y*256-top}px`;
        }
      }
    }
    for(const [key,image] of state.tileNodes) if(!visibleTiles.has(key)) {image.remove();state.tileNodes.delete(key);}
    const names=new Set();
    for(const row of points) {
      names.add(row.employee);const p=project(row);
      let pin=state.markerNodes.get(row.employee);
      if(!pin) {pin=document.createElement('button');pin.type='button';pin.className='pin';q('.markers').appendChild(pin);state.markerNodes.set(row.employee,pin);pin.onclick=()=>{state.focus=row.employee;state.follow=true;fit();render();};}
      pin.textContent=row.employee_name || row.employee;
      pin.classList.toggle('old',rowStatus(row)!=='recent');
      pin.title=`${row.employee} · ${row.company || ''} · ${rowStatus(row)} · ${row.captured_at || 'No position'} UTC`;
      pin.style.left=`${p.x*scale-left}px`;pin.style.top=`${p.y*scale-top}px`;
    }
    for(const [name,pin] of state.markerNodes) if(!names.has(name)) {pin.remove();state.markerNodes.delete(name);}
    q('.rows').replaceChildren();
    for(const row of rows) {
      const button=document.createElement('button');button.type='button';button.className='person';
      const label=document.createElement('span'),details=document.createElement('small'),status=document.createElement('span');
      label.textContent=row.employee_name || row.employee;details.textContent=`${row.employee} · ${row.company || ''}`;label.appendChild(details);status.textContent=rowStatus(row) || 'unavailable';button.append(label,status);
      button.onclick=()=>{state.focus=row.employee;state.follow=true;fit();render();};q('.rows').appendChild(button);
    }
  }
  const onRoute = () => frappe.get_route()[0] === 'employee-live-location';
  async function refresh() {
    if(state.busy || !state.active || document.hidden || !onRoute()) return;
    state.busy=true;const generation=state.generation,user=frappe.session.user;
    try {
      const response=await frappe.call({method:'rivora.live_location.latest',type:'GET'});
      if(!state.active || generation!==state.generation || user!==frappe.session.user || !onRoute()) return;
      if(response.exc || !Array.isArray(response.message?.employees)) throw Error('Invalid location response');
      state.rows=response.message.employees;state.loaded=Date.now();
      q('.state').textContent=__('Automatic updates')+' · '+new Date().toLocaleTimeString();
      if(state.follow) fit();render();
    } catch(error) {
      if(generation!==state.generation || !state.active) return;
      if(error.status===401 || error.status===403) state.rows=[];
      q('.state').textContent=__('Connection unavailable or access denied. Last received positions may be old.');render();
    } finally {state.busy=false;}
  }
  function stop() {state.active=false;state.generation++;clearInterval(state.timer);state.timer=null;}
  function start() {if(state.active) return;state.active=true;state.timer=setInterval(refresh,5000);refresh();}
  q('.search').oninput=()=>{if(state.follow) fit();render();};
  q('.zoom-in').onclick=()=>{state.z=Math.min(18,state.z+1);render();};
  q('.zoom-out').onclick=()=>{state.z=Math.max(2,state.z-1);render();};
  q('.fit').onclick=()=>{state.focus=null;state.follow=true;fit();render();};
  map.onpointerdown=event=>{if(event.target.closest('button,a')) return;state.dragging={x:event.clientX,y:event.clientY};state.follow=false;map.setPointerCapture(event.pointerId);};
  map.onpointermove=event=>{if(!state.dragging) return;const scale=2**state.z*256;state.x=((state.x-(event.clientX-state.dragging.x)/scale)%1+1)%1;state.y=Math.max(0,Math.min(1,state.y-(event.clientY-state.dragging.y)/scale));state.dragging={x:event.clientX,y:event.clientY};render();};
  map.onpointerup=map.onpointercancel=()=>{state.dragging=null;};
  const observer=new ResizeObserver(()=>{if(state.follow) fit();render();});observer.observe(map);
  document.addEventListener('visibilitychange',()=>{if(document.hidden) stop();else if(onRoute()) start();});
  frappe.router.on('change',()=>{if(onRoute() && !document.hidden) start();else stop();});
  $(wrapper).on('show',()=>{if(!document.hidden) start();}).on('hide',stop);
  wrapper.rivora_live_map={start,stop,refresh};
  if(onRoute() && !document.hidden) start();
};
