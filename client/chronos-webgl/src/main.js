import * as pc from 'playcanvas';

const canvas = document.getElementById('chronos-webgl');
const app = new pc.Application(canvas, { keyboard: new pc.Keyboard(window), mouse: new pc.Mouse(canvas), touch: new pc.TouchDevice(canvas) });
app.setCanvasFillMode(pc.FILLMODE_FILL_WINDOW);
app.setCanvasResolution(pc.RESOLUTION_AUTO);
app.scene.ambientLight = new pc.Color(.22,.3,.34);
app.start();

const state = { zone:'reception', elevatorPowered:false, logRecovered:false };
const held = new Set();
const solids = [];
const interactables = [];
const colors = { wall:new pc.Color(.38,.46,.48), floor:new pc.Color(.12,.17,.18), cyan:new pc.Color(.05,.65,.68), amber:new pc.Color(.9,.48,.08) };

function box(name, position, scale, color, solid=true) {
  const entity=new pc.Entity(name); entity.addComponent('render',{type:'box'}); entity.setPosition(...position); entity.setLocalScale(...scale);
  const material=new pc.StandardMaterial(); material.diffuse=color; material.metalness=.08; material.gloss=.35; material.update(); entity.render.material=material;
  app.root.addChild(entity); if(solid)solids.push({entity,half:{x:scale[0]/2+.45,z:scale[2]/2+.45}}); return entity;
}
function labelObject(id,label,position,color,action) { const entity=box(label,position,[1.3,1.8,.5],color,true);interactables.push({id,label,entity,action});return entity; }
function room(centerZ, accent) {
  box('floor',[0,-.15,centerZ],[20,.3,18],colors.floor,false); box('ceiling',[0,4.2,centerZ],[20,.2,18],new pc.Color(.18,.23,.24),false);
  box('left wall',[-10,2,centerZ],[.35,4,18],colors.wall); box('right wall',[10,2,centerZ],[.35,4,18],colors.wall);
  box('rear wall',[0,2,centerZ-9],[20,4,.35],colors.wall); box('front wall L',[-6,2,centerZ+9],[8,4,.35],colors.wall); box('front wall R',[6,2,centerZ+9],[8,4,.35],colors.wall);
  box('light',[0,3.95,centerZ],[7,.08,.35],accent,false);
}
room(0,colors.cyan); room(-28,colors.amber);
box('reception desk',[0,.65,2.5],[6,1.3,1.2],new pc.Color(.12,.27,.3));
labelObject('reception_terminal','RECEPČNÍ TERMINÁL',[0,1.05,1.65],colors.cyan,()=>{state.elevatorPowered=true;setStory('Napájení obnoveno. Výtah do laboratoře je připraven.');});
labelObject('lab_elevator','VÝTAH DO LABORATOŘE',[0,1, -8.6],colors.amber,()=>{if(!state.elevatorPowered){setStory('Výtah je bez napájení.');return}teleport('laboratory',[0,1.7,-21]);});
labelObject('elara_log','NOUZOVÝ ZÁZNAM ELARY',[0,1,-31],colors.cyan,()=>{state.logRecovered=true;setStory('„Jestli tohle slyšíte, časová kotva stále drží…“ Návratový portál je aktivní.');});
labelObject('return_portal','NÁVRATOVÝ PORTÁL',[0,1,-36.6],colors.amber,()=>{if(!state.logRecovered){setStory('Portál čeká na Elařin záznam.');return}window.parent?.postMessage({type:'chronos.webgl.complete'},location.origin);setStory('Vertikální řez dokončen. Můžete se vrátit do komunikátoru.');});

const camera=new pc.Entity('player'); camera.addComponent('camera',{clearColor:new pc.Color(.025,.055,.065),farClip:80,fov:68}); camera.setPosition(0,1.7,7); app.root.addChild(camera);
const sun=new pc.Entity('sun');sun.addComponent('light',{type:'directional',color:new pc.Color(.75,.88,.9),intensity:1.15,castShadows:true});sun.setEulerAngles(52,28,0);app.root.addChild(sun);
let yaw=0,pitch=0;

function setStory(text){document.getElementById('story').textContent=text;}
function teleport(zone,position){state.zone=zone;camera.setPosition(...position);document.getElementById('zone').textContent=zone==='laboratory'?'−1 · CHRONÁLNÍ LABORATOŘ':'PŘÍZEMÍ · RECEPCE';}
function nearest(){let result=null,best=2.8;for(const item of interactables){const d=camera.getPosition().distance(item.entity.getPosition());if(d<best){best=d;result=item}}return result;}
function collides(x,z){return solids.some(({entity,half})=>{const p=entity.getPosition();return Math.abs(x-p.x)<half.x&&Math.abs(z-p.z)<half.z});}
function interact(){const item=nearest();if(item)item.action();}

window.addEventListener('keydown',event=>{held.add(event.code);if(event.code==='KeyE')interact();});
window.addEventListener('keyup',event=>held.delete(event.code)); window.addEventListener('blur',()=>held.clear());
canvas.addEventListener('click',()=>canvas.requestPointerLock?.());
document.addEventListener('mousemove',event=>{if(document.pointerLockElement!==canvas)return;yaw-=event.movementX*.12;pitch=Math.max(-70,Math.min(70,pitch-event.movementY*.1));});
document.querySelectorAll('[data-move]').forEach(button=>{const key=button.dataset.move;button.addEventListener('pointerdown',e=>{e.preventDefault();held.add(key)});['pointerup','pointercancel','pointerleave'].forEach(type=>button.addEventListener(type,()=>held.delete(key)));});
document.getElementById('interact').addEventListener('click',interact);
document.getElementById('exit').addEventListener('click',()=>window.parent?.postMessage({type:'chronos.webgl.exit'},location.origin));
document.addEventListener('visibilitychange',()=>{if(document.hidden)held.clear();});

app.on('update',dt=>{
  if(document.hidden)return;
  yaw+=((held.has('ArrowLeft')||held.has('turn-left')?1:0)-(held.has('ArrowRight')||held.has('turn-right')?1:0))*95*dt;
  camera.setEulerAngles(pitch,yaw,0);
  const forward=(held.has('KeyW')||held.has('ArrowUp')||held.has('forward')?1:0)-(held.has('KeyS')||held.has('ArrowDown')||held.has('backward')?1:0);
  const side=(held.has('KeyD')||held.has('right')?1:0)-(held.has('KeyA')||held.has('left')?1:0);
  if(forward||side){const angle=yaw*Math.PI/180,step=4.2*dt,dx=(-Math.sin(angle)*forward+Math.cos(angle)*side)*step,dz=(-Math.cos(angle)*forward-Math.sin(angle)*side)*step,p=camera.getPosition();if(!collides(p.x+dx,p.z))camera.setPosition(p.x+dx,p.y,p.z);p.copy(camera.getPosition());if(!collides(p.x,p.z+dz))camera.setPosition(p.x,p.y,p.z+dz);}
  const item=nearest();document.getElementById('prompt').textContent=item?`E · ${item.label}`:(document.pointerLockElement===canvas?'WASD pohyb · myš rozhled':'Kliknutím vstoupíte do 3D prostoru');
});
window.addEventListener('resize',()=>app.resizeCanvas());
