import * as pc from 'playcanvas';

(async()=>{
if(window.parent!==window)document.documentElement.classList.add('embedded');
const world=await fetch('./worlds/chronos-institute.json',{cache:'no-store'}).then(response=>{
  if(!response.ok)throw new Error(`Mapa areálu se nenačetla (${response.status}).`);
  return response.json();
});
const canvas=document.getElementById('chronos-webgl');
const bootStatus=document.getElementById('boot-status');
if(!canvas)throw new Error('V dokumentu chybí kreslicí plocha.');
if(!window.WebGLRenderingContext)throw new Error('Tento prohlížeč nebo zařízení nepodporuje WebGL. Zapněte hardwarovou akceleraci a zkuste stránku načíst znovu.');

// Firefox může při obnovení skrytého iframe vytvořit framebuffer 0×0.
// Konzervativní kontext a omezené DPR snižují také tlak na SWGL/integrované GPU.
const app=new pc.Application(canvas,{graphicsDeviceOptions:{antialias:false,alpha:false,preserveDrawingBuffer:false,powerPreference:'high-performance'}});
if(!app.graphicsDevice)throw new Error('WebGL kontext se nepodařilo vytvořit. Zapněte hardwarovou akceleraci nebo aktualizujte ovladač grafiky.');
app.graphicsDevice.maxPixelRatio=Math.min(window.devicePixelRatio||1,1.5);
app.setCanvasFillMode(pc.FILLMODE_FILL_WINDOW);
app.setCanvasResolution(pc.RESOLUTION_AUTO);
app.scene.ambientLight=new pc.Color(.48,.54,.56);

const C={
  concrete:new pc.Color(.43,.5,.51),dark:new pc.Color(.12,.17,.18),floor:new pc.Color(.2,.27,.28),
  glass:new pc.Color(.18,.5,.58),cyan:new pc.Color(0,.9,.9),amber:new pc.Color(1,.55,.08),
  violet:new pc.Color(.65,.22,.9),grass:new pc.Color(.18,.42,.23),field:new pc.Color(.12,.5,.25),
  water:new pc.Color(.05,.36,.55),wood:new pc.Color(.5,.31,.16),white:new pc.Color(.85,.9,.88),
  room:new pc.Color(.5,.43,.36),lab:new pc.Color(.34,.5,.54),future:new pc.Color(.16,.75,.65)
};
const checkpointColors={cyan:C.cyan,amber:C.amber,violet:C.violet};
const obstacles=[];
const checkpointEntities=new Map();
const statusById={};
const levelHeight=id=>Number(world.levels.find(level=>level.id===id)?.height||0);
const materialCache=new Map();

function makeMaterial(color,{emissive=false,opacity=1}={}){
  const key=[color.r,color.g,color.b,emissive,opacity].join(':');
  if(materialCache.has(key))return materialCache.get(key);
  const result=new pc.StandardMaterial();result.diffuse=color;result.opacity=opacity;
  if(emissive)result.emissive=color;
  if(opacity<1){result.blendType=pc.BLEND_NORMAL;result.depthWrite=false;}
  result.update();materialCache.set(key,result);return result;
}

function primitive(type,name,position,scale,color,options={}){
  const entity=new pc.Entity(name);entity.addComponent('model',{type});
  entity.setPosition(...position);entity.setLocalScale(...scale);entity.model.material=makeMaterial(color,options);app.root.addChild(entity);
  if(options.collide)obstacles.push({x:position[0],y:position[1],z:position[2],hx:scale[0]/2,hz:scale[2]/2,minY:position[1]-scale[1]/2,maxY:position[1]+scale[1]/2});
  return entity;
}
const box=(name,p,s,c,o={})=>primitive('box',name,p,s,c,o);
const cylinder=(name,p,s,c,o={})=>primitive('cylinder',name,p,s,c,o);
const wall=(name,p,s,c=C.concrete)=>box(name,p,s,c,{collide:true});
const slab=(name,x,y,z,sx,sz,c=C.floor)=>box(name,[x,y-.15,z],[sx,.3,sz],c);

function buildStair(definition){
  const fromY=levelHeight(definition.from_level),toY=levelHeight(definition.to_level),steps=14;
  for(let index=0;index<steps;index++){
    const t=index/(steps-1),z=definition.z_from+(definition.z_to-definition.z_from)*t,y=fromY+(toY-fromY)*t;
    box(`${definition.name} ${index+1}`,[(definition.x1+definition.x2)/2,y-.1,z],[definition.x2-definition.x1,.2,.78],C.concrete);
    // Sloupky a krátká madla kopírují sklon bez efektu plné lamelové stěny.
    for(const [side,label] of [[definition.x1-.11,'L'],[definition.x2+.11,'P']]){
      box(`${definition.name} sloupek ${label} ${index+1}`,[side,y+.72,z],[.12,1.45,.12],C.glass,{collide:true});
      box(`${definition.name} madlo ${label} ${index+1}`,[side,y+1.47,z],[.18,.12,.78],C.white);
    }
  }
}

function buildStairShaftGuards(){
  const shaft={x1:8.5,x2:16.5,z1:-4.5,z2:6.5};
  const guardSegment=(name,x,y,z,sx,sz)=>{
    box(`${name} spodní příčka`,[x,y+.55,z],[sx,.1,sz],C.glass,{collide:true});
    box(`${name} madlo`,[x,y+1.15,z],[sx,.12,sz],C.white);
  };
  const postsAlongZ=(name,x,y)=>{
    for(let z=shaft.z1;z<=shaft.z2+.01;z+=2.2)box(`${name} sloupek ${z}`,[x,y+.58,z],[.12,1.16,.12],C.glass);
    guardSegment(name,x,y,(shaft.z1+shaft.z2)/2,.14,shaft.z2-shaft.z1);
  };
  const complement=(openings)=>{
    const sorted=openings.map(([a,b])=>[Math.max(shaft.x1,a-.35),Math.min(shaft.x2,b+.35)]).sort((a,b)=>a[0]-b[0]);
    const result=[];let cursor=shaft.x1;
    for(const [start,end] of sorted){if(start>cursor)result.push([cursor,start]);cursor=Math.max(cursor,end);}
    if(cursor<shaft.x2)result.push([cursor,shaft.x2]);return result;
  };
  for(const level of world.levels){
    const y=levelHeight(level.id),incident=world.stairs.filter(stair=>!stair.exterior&&(stair.from_level===level.id||stair.to_level===level.id));
    if(!incident.length)continue;
    postsAlongZ(`${level.name} · zábradlí šachty Z`,shaft.x1,y);
    postsAlongZ(`${level.name} · zábradlí šachty V`,shaft.x2,y);
    for(const [z,label] of [[shaft.z1,'J'],[shaft.z2,'S']]){
      const openings=incident.filter(stair=>Math.abs((stair.from_level===level.id?stair.z_from:stair.z_to)-z)<1).map(stair=>[stair.x1,stair.x2]);
      for(const [start,end] of complement(openings)){
        const width=end-start;if(width<.25)continue;const x=(start+end)/2;
        guardSegment(`${level.name} · zábradlí šachty ${label}`,x,y,z,width,.14);
        for(const px of [start,end])box(`${level.name} · sloupek šachty ${label}`,[px,y+.58,z],[.12,1.16,.12],C.glass);
      }
    }
  }
}

function buildMainShell(){
  // Přízemí se skutečnými otvory pro obě schodiště.
  slab('přízemí sever',0,0,10.5,36,9);
  slab('přízemí jih',0,0,-8.5,36,9);
  slab('přízemí střed západ',-4.75,0,1,26.5,10);slab('přízemí střed východ',17.25,0,1,1.5,10);
  // Obvod přízemí: dveře ven na jih a průchod do bowlingu na západ.
  wall('přízemí severní stěna',[0,2,15],[36,4,.35]);
  wall('přízemí jižní stěna krajní',[-17.75,2,-13],[.5,4,.35]);wall('přízemí jižní stěna L',[-8.25,2,-13],[10.5,4,.35]);wall('přízemí jižní stěna P',[10.5,2,-13],[15,4,.35]);
  wall('přízemí východní stěna',[18,2,1],[.35,4,28]);
  wall('přízemí západ sever',[-18,2,9],[.35,4,12]);wall('přízemí západ jih',[-18,2,-8],[.35,4,10]);
  wall('recepce přepážka L',[-5,1,6],[4,2,1],C.glass);wall('recepce přepážka P',[5,1,6],[4,2,1],C.glass);
  box('recepční pult',[0,.65,8],[7,1.3,1.3],C.glass,{collide:true});

  // B1 · laboratoře a archiv. U bezpečnostního schodiště zůstává skutečný otvor do B2.
  slab('B1 sever',0,-5,10.5,36,9,C.dark);slab('B1 jih',0,-5,-8.5,36,9,C.dark);
  slab('B1 střed západ',-4.75,-5,1,26.5,10,C.dark);slab('B1 střed východ',17.25,-5,1,1.5,10,C.dark);
  wall('B1 sever',[0,-3,15],[36,4,.35],C.lab);wall('B1 jih krajní',[-17.75,-3,-13],[.5,4,.35],C.lab);wall('B1 jih',[2.25,-3,-13],[31.5,4,.35],C.lab);
  wall('B1 západ',[-18,-3,1],[.35,4,28],C.lab);wall('B1 východ',[18,-3,1],[.35,4,28],C.lab);
  wall('B1 centrální přepážka L',[-4.75,-3,1],[26.5,4,.3],C.glass);wall('B1 centrální přepážka P',[17.25,-3,1],[1.5,4,.3],C.glass);
  for(const x of [-13,-7,7])box('laboratorní pult',[x,-4.35,-5],[4,1.3,2],C.glass,{collide:true});

  // B2 · stíněná chronální hala s finálním strojem času.
  slab('B2 chronální hala',0,-9,1,36,28,new pc.Color(.1,.13,.17));
  wall('B2 sever',[0,-7,15],[36,4,.35],C.dark);wall('B2 jih',[0,-7,-13],[36,4,.35],C.dark);
  wall('B2 západ',[-18,-7,1],[.35,4,28],C.dark);wall('B2 východ',[18,-7,1],[.35,4,28],C.dark);
  wall('B2 stínění L',[-10,-7,2],[12,4,.35],C.violet);wall('B2 stínění P1',[6.25,-7,2],[4.5,4,.35],C.violet);wall('B2 stínění P2',[15.25,-7,2],[1.5,4,.35],C.violet);
  cylinder('reaktor stroje času',[7,-7.4,-4],[4.4,3.2,4.4],C.violet,{emissive:true,collide:true});
  for(const x of [-12,-6,0,12])box('B2 řídicí pult',[x,-8.35,9],[3.2,1.3,1.4],C.future,{emissive:true,collide:true});

  // Samostatný a dobře viditelný únikový východ z B1 do venkovního areálu.
  box('Únikový východ · levá zárubeň',[-17.25,-3,-12.85],[.2,3.8,.2],C.dark);
  box('Únikový východ · pravá zárubeň',[-13.75,-3,-12.85],[.2,3.8,.2],C.dark);
  box('Únikový východ · nadpraží',[-15.5,-1.2,-12.85],[3.7,.2,.2],C.dark);
  box('Únikový východ · označení',[-15.5,-1.45,-12.7],[2.5,.45,.12],new pc.Color(.08,.85,.35),{emissive:true});

  // První patro s otvory u obou schodišť.
  slab('1P sever',0,4,10.5,36,9,C.room);slab('1P jih',0,4,-8.5,36,9,C.room);
  slab('1P střed západ',-4.75,4,1,26.5,10,C.room);slab('1P střed východ',17.25,4,1,1.5,10,C.room);
  wall('1P severní stěna',[0,6,15],[36,4,.35],C.room);wall('1P jižní stěna',[0,6,-13],[36,4,.35],C.room);
  wall('1P západní stěna',[-18,6,1],[.35,4,28],C.room);
  wall('1P východ sever',[18,6,13.5],[.35,4,3],C.room);wall('1P východ jih',[18,6,-3],[.35,4,18],C.room);
  for(const x of [-13,-7,7]){
    wall(`1P příčka ${x}`,[x,6,7],[.25,4,12],C.room);
    box(`1P lůžko ${x}`,[x+2,4.45,10],[2.5,.8,4],C.white,{collide:true});
  }

  // Druhé patro – klidnější hostovské pokoje.
  slab('2P sever',0,8,10.5,36,9,C.room);slab('2P jih',0,8,-8.5,36,9,C.room);
  slab('2P střed západ',-4.75,8,1,26.5,10,C.room);slab('2P střed východ',17.25,8,1,1.5,10,C.room);
  wall('2P sever',[0,10,15],[36,4,.35],C.room);wall('2P jih',[0,10,-13],[36,4,.35],C.room);
  wall('2P západ',[-18,10,1],[.35,4,28],C.room);wall('2P východ',[18,10,1],[.35,4,28],C.room);
  for(const z of [-8,8])for(const [x,width] of [[-13.5,9],[-4,6],[4,6],[13.5,9]])wall(`2P příčka ${z} / ${x}`,[x,10,z],[width,4,.25],C.room);
  for(const [x,width] of [[-4.75,26.5],[17.25,1.5]])wall(`2P příčka 0 / ${x}`,[x,10,0],[width,4,.25],C.room);
  for(const [x,z] of [[-13,-10],[-5,-10],[5,-10],[13,-10],[-13,4],[-5,4],[5,4],[13,11]])box('hostovské lůžko',[x,8.45,z],[2.5,.8,3.8],C.white,{collide:true});
}

function buildBowling(){
  slab('bowlingová podlaha',-27,0,.5,18,21,C.wood);
  wall('bowling západ',[-36,2,.5],[.35,4,21],C.dark);wall('bowling sever',[-27,2,11],[18,4,.35],C.dark);wall('bowling jih',[-27,2,-10],[18,4,.35],C.dark);
  for(let lane=0;lane<4;lane++){
    const x=-33+lane*3.7;box(`bowling dráha ${lane+1}`,[x,.03,-1],[2.7,.08,15],new pc.Color(.62,.4,.2));
    for(let pin=0;pin<3;pin++)cylinder('kuželka',[x+(pin-1)*.45,.45,-7+Math.abs(pin-1)*.4],[.22,.8,.22],C.white);
  }
  for(const x of [-31,-27,-23])box('bowlingové křeslo',[x,.55,8],[2,1.1,2],C.violet,{collide:true});
}

function buildTerraceAndOutdoors(){
  slab('vyhlídková terasa',28,4,8.5,20,11,new pc.Color(.35,.38,.3));
  wall('terasa severní zábradlí',[28,4.75,14],[20,1.5,.18],C.glass);
  wall('terasa jižní zábradlí L',[25.5,4.75,3],[15,1.5,.18],C.glass);wall('terasa jižní zábradlí P',[37.5,4.75,3],[1,1.5,.18],C.glass);
  wall('terasa východní zábradlí',[38,4.75,8.5],[.18,1.5,11],C.glass);
  for(const x of [22,28,34])box('terasová lavička',[x,4.45,10],[3,.8,1],C.wood,{collide:true});

  slab('venkovní trávník',15,-.05,-25,80,38,C.grass);
  slab('cesta k hřišti',8,0,-17,8,12,new pc.Color(.35,.34,.3));slab('cesta k rybníku',26,0,-22,6,20,new pc.Color(.35,.34,.3));
  slab('servisní dvůr',7,.01,-18,12,8,C.concrete);
  for(const [x,z] of [[3,-16],[7,-16],[11,-16],[3,-20],[7,-20],[11,-20]])cylinder('fázový senzor',[x,.5,z],[.3,1,.3],C.amber,{emissive:true});
  slab('sportovní hřiště',28,.02,-10,28,15,C.field);
  for(const x of [16,40])wall('postranní čára',[x,.04,-10],[.12,.04,14],C.white);
  for(const z of [-17,-3])wall('branková čára',[28,.04,z],[24,.04,.12],C.white);
  wall('středová čára',[28,.04,-10],[.12,.04,14],C.white);
  for(const x of [17,39]){wall('branka',[x,1,-10],[.15,2,5],C.white);wall('břevno',[x,2,-10],[.15,.15,5],C.white);}
  box('sportovní servisní domek',[43,1.5,-14],[6,3,7],C.dark,{collide:true});

  cylinder('rybník',[34,-.08,-30],[18,.12,13],C.water,{emissive:true});
  slab('molo',34,.18,-23,4,12,C.wood);
  for(const [x,z] of [[-10,-21],[-3,-34],[8,-27],[47,-26],[45,-39],[15,-40]]){
    cylinder('kmen',[x,1,z],[.55,2.5,.55],C.wood,{collide:true});cylinder('koruna',[x,3,z],[3.2,3.2,3.2],C.grass);
  }
}

function buildCheckpoints(){
  for(const point of world.checkpoints){
    const color=checkpointColors[point.color]||C.cyan,[x,y,z]=point.position;
    box(`${point.label} · skříň`,[x,y-.08,z],[1.45,1.75,.72],C.dark,{collide:true});
    box(`${point.label} · konzole`,[x,y+.72,z],[1.7,.18,.92],C.concrete);
    const entity=box(`${point.label} · obrazovka`,[x,y+.22,z-.4],[1.08,.58,.08],color,{emissive:true});
    checkpointEntities.set(point.id,{...point,entity,baseColor:color});
  }
  const room=world.optional_room,[x,y,z]=room.position;
  box(`${room.label} · dveře`,[x,y,z],[1.5,2,.45],C.dark,{collide:true});
  const entity=box(`${room.label} · panel`,[x+.5,y+.15,z-.26],[.32,.52,.08],C.violet,{emissive:true});
  checkpointEntities.set(room.id,{...room,entity,baseColor:C.violet,interaction:'room'});
}

buildMainShell();buildBowling();buildTerraceAndOutdoors();world.stairs.forEach(buildStair);buildStairShaftGuards();buildCheckpoints();

const camera=new pc.Entity('player');camera.addComponent('camera',{clearColor:new pc.Color(.09,.18,.22),nearClip:.08,farClip:150,fov:68});
camera.setPosition(world.spawn.x,world.spawn.y,world.spawn.z);camera.lookAt(...world.spawn.look_at);app.root.addChild(camera);
const sun=new pc.Entity('sun');sun.addComponent('light',{type:'directional',color:pc.Color.WHITE,intensity:1.65,castShadows:false});sun.setEulerAngles(52,28,0);app.root.addChild(sun);
for(const [x,y,z,color] of [[0,3,7,C.cyan],[-27,3,0,C.amber],[0,-2,0,C.cyan],[8,-7,-2,C.violet],[28,7,8,C.amber]]){const light=new pc.Entity('zónové světlo');light.addComponent('light',{type:'omni',color,intensity:1.2,range:15,castShadows:false});light.setPosition(x,y,z);app.root.addChild(light);}
app.start();
bootStatus.hidden=true;

let contextLost=false;
canvas.addEventListener('webglcontextlost',event=>{
  event.preventDefault();contextLost=true;
  const panel=document.getElementById('fatal');panel.hidden=false;
  panel.textContent='WEBGL KONTEXT BYL ZTRACEN. Čekám na obnovení rendereru…';
});
canvas.addEventListener('webglcontextrestored',()=>{
  contextLost=false;document.getElementById('fatal').hidden=true;scheduleResize();
  showTransient('3D renderer byl obnoven.',3000);
});

let currentLevel=Number(world.spawn.level),futureLayer=false,paused=false;
const held=new Set(),initialView=camera.getEulerAngles();let yaw=initialView.y,pitch=initialView.x;
const keyMap={KeyW:'forward',ArrowUp:'forward',KeyS:'backward',ArrowDown:'backward',KeyA:'left',KeyD:'right',ArrowLeft:'turn-left',ArrowRight:'turn-right'};

function stairAt(x,z){return world.stairs.find(stair=>x>=stair.x1&&x<=stair.x2&&z>=Math.min(stair.z_from,stair.z_to)-.3&&z<=Math.max(stair.z_from,stair.z_to)+.3&&(currentLevel===stair.from_level||currentLevel===stair.to_level));}
function groundHeight(x,z){const stair=stairAt(x,z);if(!stair)return levelHeight(currentLevel);const t=Math.max(0,Math.min(1,(z-stair.z_from)/(stair.z_to-stair.z_from)));return levelHeight(stair.from_level)+(levelHeight(stair.to_level)-levelHeight(stair.from_level))*t;}
function updateStairLevel(x,z){const stair=stairAt(x,z);if(!stair)return;if(Math.abs(z-stair.z_to)<.45)currentLevel=stair.to_level;else if(Math.abs(z-stair.z_from)<.45)currentLevel=stair.from_level;}
function walkable(x,z){
  if(stairAt(x,z))return true;
  if(currentLevel===-2||currentLevel===-1||currentLevel===2)return x>=-17.5&&x<=17.5&&z>=-12.5&&z<=14.5;
  if(currentLevel===1)return x>=-17.5&&x<=38&&z>=-12.5&&z<=14.5&&(x<=18.5||z>=2.7);
  return x>=-43&&x<=50&&z>=-44&&z<=15;
}
function blocked(x,z,height){
  const pond=((x-34)/9)**2+((z+30)/6.5)**2<1.04,onPier=x>=31.5&&x<=36.5&&z>=-29.5&&z<=-16.5;
  if(currentLevel===0&&pond&&!onPier)return true;
  const radius=.42,bodyBottom=height+.08,bodyTop=height+1.65;
  return obstacles.some(item=>bodyTop>item.minY&&bodyBottom<item.maxY&&Math.abs(x-item.x)<item.hx+radius&&Math.abs(z-item.z)<item.hz+radius);
}
function currentZone(){
  const p=camera.getPosition(),stair=stairAt(p.x,p.z);if(stair)return stair.name;
  const matches=world.zones.filter(zone=>zone.level===currentLevel&&p.x>=zone.bounds[0]&&p.x<=zone.bounds[1]&&p.z>=zone.bounds[2]&&p.z<=zone.bounds[3]);
  matches.sort((a,b)=>(a.bounds[1]-a.bounds[0])*(a.bounds[3]-a.bounds[2])-(b.bounds[1]-b.bounds[0])*(b.bounds[3]-b.bounds[2]));
  return matches[0]?.name||world.levels.find(level=>level.id===currentLevel)?.name||'AREÁL';
}
function activeTarget(){return world.checkpoints.find(point=>['available','active'].includes(statusById[point.id]))||null;}
function nearestCheckpoint(){const p=camera.getPosition();return [...checkpointEntities.values()].filter(point=>point.level===currentLevel).map(point=>({...point,distance:p.distance(point.entity.getPosition())})).sort((a,b)=>a.distance-b.distance)[0];}
function updateCheckpointMaterials(){
  for(const [id,point] of checkpointEntities){const status=statusById[id]||'locked';let color=status==='complete'?new pc.Color(.1,.8,.4):['available','active'].includes(status)?point.baseColor:new pc.Color(.12,.2,.21);if(futureLayer&&status!=='locked')color=C.future;point.entity.model.material=makeMaterial(color,{emissive:status!=='locked'});}
}
let transientMessage='',transientUntil=0;
function showTransient(message,duration=2400){transientMessage=message;transientUntil=performance.now()+duration;document.getElementById('story').textContent=message;}
function interact(){
  const point=nearestCheckpoint();
  if(!point||point.distance>3){showTransient('V dosahu není žádná časová kotva.');return;}
  const status=statusById[point.id]||'locked';
  if(!['available','active'].includes(status)){showTransient(status==='complete'?'Tato kotva už je stabilizovaná.':'Kotva je zatím uzamčená předchozí částí mise.');return;}
  if(point.interaction==='room'){
    document.exitPointerLock?.();held.clear();
    window.parent?.postMessage({type:'chronos.webgl.room',room_id:point.id,label:point.label},location.origin);
    showTransient(`Otevírám přístupový panel: ${point.label}.`);return;
  }
  window.parent?.postMessage({type:'chronos.webgl.checkpoint',checkpoint_id:point.id,label:point.label},location.origin);
  showTransient(`Aktivuji ${point.label}.`);
  if(window.parent===window){statusById[point.id]='complete';const index=world.checkpoints.findIndex(item=>item.id===point.id);if(world.checkpoints[index+1])statusById[world.checkpoints[index+1].id]='available';updateCheckpointMaterials();}
}
function toggleLayer(){futureLayer=!futureLayer;app.scene.ambientLight=futureLayer?new pc.Color(.22,.5,.48):new pc.Color(.48,.54,.56);camera.camera.clearColor=futureLayer?new pc.Color(.04,.2,.22):new pc.Color(.09,.18,.22);updateCheckpointMaterials();showTransient(`Časová vrstva: ${futureLayer?'BUDOUCNOST':'PŘÍTOMNOST'}.`);}
function openParentGadget(gadget){
  if(window.parent===window){showTransient('Gadgety jsou dostupné po otevření hry v Chronoterminálu.');return;}
  document.exitPointerLock?.();held.clear();paused=true;window.parent.postMessage({type:'chronos.webgl.gadget',gadget},location.origin);
}

window.addEventListener('keydown',event=>{
  const gadget={KeyI:'intercom',KeyB:'puzzles',KeyC:'cipher',KeyM:'map'}[event.code];
  if(gadget){event.preventDefault();openParentGadget(gadget);return;}
  if(paused)return;
  const action=keyMap[event.code];if(action){event.preventDefault();held.add(action);}
  if(event.code==='KeyE'){event.preventDefault();interact();}if(event.code==='KeyT'){event.preventDefault();toggleLayer();}
});
window.addEventListener('keyup',event=>{const action=keyMap[event.code];if(action)held.delete(action);});window.addEventListener('blur',()=>held.clear());
canvas.addEventListener('click',()=>{if(!paused)canvas.requestPointerLock?.();});
document.addEventListener('mousemove',event=>{if(document.pointerLockElement!==canvas)return;yaw-=event.movementX*.12;pitch=Math.max(-75,Math.min(75,pitch-event.movementY*.1));});
document.querySelectorAll('[data-move]').forEach(button=>{const action=button.dataset.move;button.addEventListener('pointerdown',event=>{event.preventDefault();held.add(action);});for(const type of ['pointerup','pointercancel','pointerleave'])button.addEventListener(type,()=>held.delete(action));});
document.getElementById('interact').addEventListener('click',interact);document.getElementById('exit').addEventListener('click',()=>window.parent?.postMessage({type:'chronos.webgl.exit'},location.origin));

window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==window.parent)return;
  if(event.data?.type==='chronos.pause'){
    paused=true;held.clear();document.exitPointerLock?.();showTransient('GADGET AKTIVNÍ · svět pozastaven',60000);return;
  }
  if(event.data?.type==='chronos.resume'){
    paused=false;transientUntil=0;showTransient('GADGET ULOŽEN · kliknutím obnovíte ovládání',1800);return;
  }
  if(event.data?.type==='chronos.progress'){
    for(const id of Object.keys(statusById))delete statusById[id];
    for(const node of event.data.progress?.nodes||[])statusById[node.id]=node.status;
    updateCheckpointMaterials();
  }
});
if(window.parent===window)statusById.reception_archive='available';
window.parent?.postMessage({type:'chronos.webgl.ready'},location.origin);
updateCheckpointMaterials();

app.on('update',dt=>{
  if(contextLost)return;
  if(paused){document.getElementById('prompt').textContent='GADGET OTEVŘEN · svět čeká';return;}
  const movementDelta=Math.min(dt,.05);
  yaw+=((held.has('turn-left')?1:0)-(held.has('turn-right')?1:0))*95*movementDelta;camera.setEulerAngles(pitch,yaw,0);
  const forward=(held.has('forward')?1:0)-(held.has('backward')?1:0),side=(held.has('right')?1:0)-(held.has('left')?1:0);
  if(forward||side){
    const direction=camera.forward.clone();direction.y=0;direction.normalize().mulScalar(forward);const right=camera.right.clone();right.y=0;right.normalize().mulScalar(side);direction.add(right);if(direction.lengthSq()>0)direction.normalize().mulScalar(5*movementDelta);
    const p=camera.getPosition();let x=p.x+direction.x,z=p.z+direction.z,height=groundHeight(x,z);
    if(!walkable(x,z)||blocked(x,z,height)){x=p.x;z=p.z+direction.z;height=groundHeight(x,z);if(!walkable(x,z)||blocked(x,z,height)){x=p.x+direction.x;z=p.z;height=groundHeight(x,z);if(!walkable(x,z)||blocked(x,z,height)){x=p.x;z=p.z;height=groundHeight(x,z);}}}
    updateStairLevel(x,z);height=groundHeight(x,z);camera.setPosition(x,height+1.7,z);
  }
  const near=nearestCheckpoint(),target=activeTarget();
  document.getElementById('prompt').textContent=near?.distance<=3?`E · POUŽÍT ${near.label}`:(document.pointerLockElement===canvas?'WASD · E zařízení · I/B/C/M gadgety':'Klikněte do světa · WASD · I/B/C/M gadgety');
  if(performance.now()>=transientUntil)document.getElementById('story').textContent=target?`AKTIVNÍ CÍL: ${target.label} · ${target.level===currentLevel?`${camera.getPosition().distance(new pc.Vec3(...target.position)).toFixed(0)} m`:world.levels.find(level=>level.id===target.level)?.name}`:'Prozkoumejte areál a čekejte na další pokyn interkomu.';
});

let resizeFrame=0;
function resize(){
  resizeFrame=0;
  const width=Math.floor(canvas.clientWidth||window.innerWidth),height=Math.floor(canvas.clientHeight||window.innerHeight);
  if(width<2||height<2)return;
  app.resizeCanvas(width,height);
}
function scheduleResize(){if(!resizeFrame)resizeFrame=requestAnimationFrame(()=>requestAnimationFrame(resize));}
if('ResizeObserver' in window)new ResizeObserver(scheduleResize).observe(canvas);
window.addEventListener('resize',scheduleResize);
window.addEventListener('pageshow',scheduleResize);
document.addEventListener('visibilitychange',()=>{held.clear();if(!document.hidden)scheduleResize();});
scheduleResize();
setInterval(()=>{document.getElementById('zone').textContent=`${currentZone()} · ${futureLayer?'BUDOUCNOST':'PŘÍTOMNOST'} · DRAW ${app.stats.drawCalls.total}`;},500);
})().catch(error=>{
  window.showChronosFatal?.(error?.message||String(error));
  console.error(error);
});
