import * as pc from 'playcanvas';

const canvas=document.getElementById('chronos-webgl');
const app=new pc.Application(canvas);
app.setCanvasFillMode(pc.FILLMODE_FILL_WINDOW);
app.setCanvasResolution(pc.RESOLUTION_AUTO);
app.scene.ambientLight=new pc.Color(.45,.5,.55);

function material(color,emissive=false){
  const value=new pc.StandardMaterial();
  value.diffuse=color;
  if(emissive)value.emissive=color;
  value.update();
  return value;
}

function cube(name,position,scale,color,emissive=false){
  const entity=new pc.Entity(name);
  entity.addComponent('model',{type:'box'});
  entity.setPosition(position[0],position[1],position[2]);
  entity.setLocalScale(scale[0],scale[1],scale[2]);
  entity.model.material=material(color,emissive);
  app.root.addChild(entity);
  return entity;
}

const camera=new pc.Entity('camera');
camera.addComponent('camera',{clearColor:new pc.Color(.08,.16,.2),nearClip:.1,farClip:100});
camera.setPosition(0,2.2,8);
camera.lookAt(0,1,0);
app.root.addChild(camera);

const light=new pc.Entity('light');
light.addComponent('light',{type:'directional',color:pc.Color.WHITE,intensity:1.8,castShadows:false});
light.setEulerAngles(45,35,0);
app.root.addChild(light);

cube('floor',[0,-.15,0],[12,.3,14],new pc.Color(.2,.3,.32));
cube('rear wall',[0,2,-6],[12,4,.3],new pc.Color(.48,.58,.62));
cube('left wall',[-6,2,0],[.3,4,12],new pc.Color(.38,.48,.52));
cube('right wall',[6,2,0],[.3,4,12],new pc.Color(.38,.48,.52));
cube('CHRONOS calibration',[0,1,0],[2,2,2],new pc.Color(0,1,1),true);
cube('reception desk',[0,.6,3],[5,1.2,1],new pc.Color(.25,.48,.52));

app.start();
document.getElementById('story').textContent='Referenční scéna: azurová kalibrační krychle na recepci.';
document.getElementById('prompt').textContent='PlayCanvas minimální režim';

function resize(){app.resizeCanvas(Math.max(1,canvas.clientWidth),Math.max(1,canvas.clientHeight));}
new ResizeObserver(resize).observe(document.documentElement);
window.addEventListener('resize',resize);
requestAnimationFrame(()=>requestAnimationFrame(resize));

setInterval(()=>{
  const size=`${app.graphicsDevice.width}×${app.graphicsDevice.height}`;
  document.getElementById('zone').textContent=`MINIMAL · DRAW ${app.stats.drawCalls.total} · ${size}`;
},1000);

document.getElementById('exit').addEventListener('click',()=>window.parent?.postMessage({type:'chronos.webgl.exit'},location.origin));
