(() => {
    'use strict';

    const FLOOR_NAMES = {'-1':'PODZEMÍ · LABORATOŘE', '0':'PŘÍZEMÍ · VEŘEJNÝ AREÁL', '1':'1. PATRO · UBIKACE'};
    const CHECKPOINTS = [
        ['reception_archive', 'Recepční archiv', 0, 17, 0, '4ec67b900c4a491ba180c8a48d5309f2'],
        ['staircase_signal', 'Schodišťový chronosignál', 0, -5, 1, '74c67eaf38ef4b72b22f5c971b7bb7bd'],
        ['courtyard_minefield', 'Nestabilní sportoviště', 18, 11, 0, '6b0f716a2a264cc783d182b93f99a531'],
        ['bowling_diagnostics', 'Binární diagnostika', -23, -7, 0, 'a9dc930b787a4be6a5344e524d56073b'],
        ['timeline_calibration', 'Kalibrace u bowlingu', -17, -15, 0, '9c6fa028b7614a669c9c43def9df1ba8'],
        ['terrace_echo', 'Chronální ozvěna terasy', 25, 16, 0, '8fd7cd0a5c844702bc384665e864d335'],
        ['courtyard_alignment', 'Zarovnání uzlů', 15, -6, 0, 'cb2ee52d5ae74fa6b68f94f59db75d63'],
        ['sports_archive', 'Archiv sportovního areálu', 25, -8, 0, 'de724be50829411287a0536095cc9148'],
        ['sports_cipher', 'Sportovní šifrovací kotva', 17, -17, 0, 'fbc646e76f0247d69589de21ea645f95'],
        ['future_archive', 'Archiv budoucnosti', -14, -11, -1, '4dc33e89b217a3a439dbb96e31c59ea4'],
        ['time_machine_console', 'Finální konzole', 14, -11, -1, 'b9ae752e80e5d4d85965e805bbc4b62f'],
    ].map(([id, name, x, y, floor, token]) => ({id, name, x, y, floor, token}));

    const ROOMS = [
        {floor:0,name:'RECEPCE', x1:-11,y1:8,x2:11,y2:23,color:'#87959c'},
        {floor:0,name:'BOWLING', x1:-33,y1:-20,x2:-10,y2:5,color:'#765c4b'},
        {floor:0,name:'SPORTOVNÍ AREÁL', x1:10,y1:-21,x2:33,y2:8,color:'#416d4d'},
        {floor:0,name:'TERASA', x1:12,y1:9,x2:33,y2:23,color:'#6d7652'},
        {floor:0,name:'CENTRÁLNÍ HALA', x1:-9,y1:-20,x2:9,y2:7,color:'#54636a'},
        {floor:-1,name:'BIOLOGICKÁ LABORATOŘ', x1:-23,y1:-18,x2:-5,y2:8,color:'#507c78'},
        {floor:-1,name:'CHRONÁLNÍ LABORATOŘ', x1:5,y1:-18,x2:23,y2:8,color:'#527b91'},
        {floor:-1,name:'PODZEMNÍ KORIDOR', x1:-23,y1:9,x2:23,y2:18,color:'#46575d'},
        {floor:1,name:'UBIKACE A', x1:-23,y1:-17,x2:-5,y2:15,color:'#8c765e'},
        {floor:1,name:'UBIKACE B', x1:5,y1:-17,x2:23,y2:15,color:'#806b59'},
        {floor:1,name:'SPOLEČENSKÁ HALA', x1:-4,y1:-17,x2:4,y2:15,color:'#62696b'},
    ];
    const WALLS = [];
    const addWall = (x1, y1, x2, y2, zone, color) => WALLS.push({x1,y1,x2,y2,zone,color});
    const wall=(floor,x1,y1,x2,y2,zone,color)=>{addWall(x1,y1,x2,y2,zone,color);WALLS[WALLS.length-1].floor=floor};
    const shell=(floor,x1,y1,x2,y2,color)=>{wall(floor,x1,y1,x2,y1,'PLÁŠŤ',color);wall(floor,x2,y1,x2,y2,'PLÁŠŤ',color);wall(floor,x2,y2,x1,y2,'PLÁŠŤ',color);wall(floor,x1,y2,x1,y1,'PLÁŠŤ',color)};
    shell(0,-34,-22,34,24,'#65747b');
    wall(0,-10,-22,-10,-3,'BOWLING','#91735d'); wall(0,-10,3,-10,24,'RECEPCE','#91735d');
    wall(0,10,-22,10,-3,'SPORT','#56885d'); wall(0,10,3,10,24,'TERASA','#56885d');
    wall(0,-10,7,-3,7,'RECEPCE','#9ca7aa'); wall(0,3,7,10,7,'RECEPCE','#9ca7aa');
    shell(-1,-24,-19,24,19,'#547079'); wall(-1,-5,-19,-5,7,'LAB A','#60918b'); wall(-1,-5,11,-5,19,'LAB A','#60918b'); wall(-1,5,-19,5,7,'LAB B','#608ca0'); wall(-1,5,11,5,19,'LAB B','#608ca0');
    shell(1,-24,-18,24,16,'#796b61'); wall(1,-5,-18,-5,-4,'UBIKACE A','#917960'); wall(1,-5,2,-5,16,'UBIKACE A','#917960'); wall(1,5,-18,5,-4,'UBIKACE B','#917960'); wall(1,5,2,5,16,'UBIKACE B','#917960');

    const PORTALS = [
        {floor:0,x:0,y:1,to:1,toX:0,toY:1,label:'SCHODIŠTĚ NA UBIKACE'},
        {floor:1,x:0,y:1,to:0,toX:0,toY:1,label:'SCHODIŠTĚ DO PŘÍZEMÍ'},
        {floor:0,x:0,y:-8,to:-1,toX:0,toY:13,label:'VÝTAH DO LABORATOŘÍ'},
        {floor:-1,x:0,y:13,to:0,toX:0,toY:-8,label:'VÝTAH DO PŘÍZEMÍ'},
    ];

    let canvas, context, progress = null, active = false, future = false;
    let player = {x:0, y:19, floor:0, heading:-Math.PI/2};
    let held = new Set(), frame = null, previousTime = 0, messageUntil = 0;

    const statusMap = () => Object.fromEntries((progress?.nodes || []).map(node => [node.id, node.status]));
    const isVisible = () => document.getElementById('tab-chronos3d')?.classList.contains('active');
    const activeCheckpoint = () => {
        const statuses = statusMap();
        return CHECKPOINTS.filter(point => ['available','active'].includes(statuses[point.id]))
            .sort((a,b) => distance(a)-distance(b))[0] || null;
    };
    const distance = point => Math.hypot(point.x-player.x, point.y-player.y) + Math.abs((point.floor||0)-player.floor)*35;
    const localDistance = point => Math.hypot(point.x-player.x, point.y-player.y);
    const currentWalls = () => WALLS.filter(w=>w.floor===player.floor);

    function initialize() {
        canvas = document.getElementById('chronos3d-canvas');
        if (!canvas || context) return;
        context = canvas.getContext('2d', {alpha:false});
        canvas.addEventListener('click', () => canvas.focus({preventScroll:true}));
        document.querySelectorAll('[data-chronos-control]').forEach(button => {
            const control = button.dataset.chronosControl;
            button.addEventListener('pointerdown', event => { event.preventDefault(); held.add(control); startLoop(); });
            for (const name of ['pointerup','pointercancel','pointerleave']) button.addEventListener(name, () => held.delete(control));
        });
        document.querySelector('[data-chronos-action="interact"]')?.addEventListener('click', interact);
        document.querySelector('[data-chronos-action="layer"]')?.addEventListener('click', toggleLayer);
        draw();
    }

    const keyMap = {KeyW:'forward',KeyS:'backward',KeyA:'strafe-left',KeyD:'strafe-right',ArrowUp:'forward',ArrowDown:'backward',ArrowLeft:'left',ArrowRight:'right'};
    document.addEventListener('keydown', event => {
        if (!isVisible() || ['INPUT','TEXTAREA','SELECT'].includes(event.target?.tagName)) return;
        if (event.code === 'KeyE') { event.preventDefault(); interact(); return; }
        if (event.code === 'KeyT') { event.preventDefault(); toggleLayer(); return; }
        if (event.code === 'KeyR') { event.preventDefault(); resetPlayer(); return; }
        const control = keyMap[event.code]; if (!control) return;
        event.preventDefault(); held.add(control); startLoop();
    });
    document.addEventListener('keyup', event => { const control=keyMap[event.code]; if(control)held.delete(control); });
    window.addEventListener('blur', () => held.clear());

    function startLoop() {
        if (frame !== null) return;
        previousTime = performance.now();
        frame = requestAnimationFrame(tick);
    }

    function tick(time) {
        frame = null;
        const delta = Math.min(.04, (time-previousTime)/1000 || 0); previousTime=time;
        if (active && isVisible()) updateMovement(delta);
        draw();
        if (active && isVisible() && (held.size || time < messageUntil)) frame=requestAnimationFrame(tick);
    }

    function updateMovement(delta) {
        const turn=(held.has('left')?1:0)-(held.has('right')?1:0);
        player.heading += turn*1.9*delta;
        let forward=(held.has('forward')?1:0)-(held.has('backward')?1:0);
        let strafe=(held.has('strafe-right')?1:0)-(held.has('strafe-left')?1:0);
        const length=Math.hypot(forward,strafe)||1; forward/=length; strafe/=length;
        const speed=5.8, dx=(Math.cos(player.heading)*forward+Math.cos(player.heading+Math.PI/2)*strafe)*speed*delta;
        const dy=(Math.sin(player.heading)*forward+Math.sin(player.heading+Math.PI/2)*strafe)*speed*delta;
        moveWithCollision(dx,dy);
    }

    function moveWithCollision(dx,dy) {
        const radius=.55;
        const blocked=(x,y)=>currentWalls().some(w=>pointSegmentDistance(x,y,w.x1,w.y1,w.x2,w.y2)<radius);
        if(!blocked(player.x+dx,player.y))player.x+=dx;
        if(!blocked(player.x,player.y+dy))player.y+=dy;
    }

    function pointSegmentDistance(px,py,x1,y1,x2,y2) {
        const dx=x2-x1,dy=y2-y1,length=dx*dx+dy*dy||1;
        const t=Math.max(0,Math.min(1,((px-x1)*dx+(py-y1)*dy)/length));
        return Math.hypot(px-(x1+t*dx),py-(y1+t*dy));
    }

    function rayHit(angle,maxDistance=70) {
        const dx=Math.cos(angle),dy=Math.sin(angle); let best=null;
        for(const wall of currentWalls()){
            const sx=wall.x2-wall.x1,sy=wall.y2-wall.y1,den=dx*sy-dy*sx;
            if(Math.abs(den)<1e-8)continue;
            const ax=wall.x1-player.x,ay=wall.y1-player.y;
            const ray=(ax*sy-ay*sx)/den,along=(ax*dy-ay*dx)/den;
            if(ray>.03&&ray<maxDistance&&along>=0&&along<=1&&(!best||ray<best.distance))best={distance:ray,wall};
        }
        return best;
    }

    function draw() {
        if(!context)return;
        const w=canvas.width,h=canvas.height,horizon=h*.48;
        const sky=context.createLinearGradient(0,0,0,horizon); sky.addColorStop(0,future?'#102d35':'#07131d'); sky.addColorStop(1,future?'#2b6f72':'#36505d');
        context.fillStyle=sky;context.fillRect(0,0,w,horizon);
        const floor=context.createLinearGradient(0,horizon,0,h);floor.addColorStop(0,future?'#183c3b':'#3a3d3c');floor.addColorStop(1,'#050808');context.fillStyle=floor;context.fillRect(0,horizon,w,h-horizon);
        const fov=Math.PI/3,column=4,focal=w/(2*Math.tan(fov/2));
        for(let x=0;x<w;x+=column){
            const offset=(x/w-.5)*fov,hit=rayHit(player.heading+offset); if(!hit)continue;
            const corrected=Math.max(.15,hit.distance*Math.cos(offset)),height=Math.min(h*2.2,focal*4.2/corrected),top=horizon-height*.5;
            const shade=Math.max(.18,1-hit.distance/55),base=hexRgb(hit.wall.color),pulse=future?.72+.18*Math.sin(performance.now()/420+hit.distance):1;
            context.fillStyle=`rgb(${base.map(value=>Math.round(value*shade*pulse)).join(',')})`;context.fillRect(x,top,column+1,height);
            if(future&&x%12<4){context.fillStyle='rgba(70,255,230,.13)';context.fillRect(x,top,column,height)}
        }
        drawMarkers(fov,focal,horizon); drawPortals(fov,focal,horizon); drawMinimap(); updateHud();
        if(!progress){context.fillStyle='#9ff';context.font='20px monospace';context.textAlign='center';context.fillText('ČEKÁM NA HERNI STAV…',w/2,h/2)}
    }

    function drawMarkers(fov,focal,horizon) {
        const statuses=statusMap();
        CHECKPOINTS.filter(point=>point.floor===player.floor).sort((a,b)=>localDistance(b)-localDistance(a)).forEach(point=>{
            const dx=point.x-player.x,dy=point.y-player.y,d=localDistance(point);let angle=Math.atan2(dy,dx)-player.heading;
            while(angle>Math.PI)angle-=Math.PI*2;while(angle<-Math.PI)angle+=Math.PI*2;
            if(Math.abs(angle)>fov*.56||d<.7)return;
            const obstruction=rayHit(player.heading+angle,d);if(obstruction&&obstruction.distance<d-.5)return;
            const x=canvas.width*(.5+angle/fov),size=Math.max(9,Math.min(54,focal*.72/d)),status=statuses[point.id]||'locked';
            context.fillStyle=status==='complete'?'#28df8b':['available','active'].includes(status)?'#ffe253':'#48545a';context.strokeStyle='#001';context.lineWidth=3;
            context.beginPath();context.moveTo(x,horizon-size*1.7);context.lineTo(x-size*.58,horizon-size*.68);context.lineTo(x+size*.58,horizon-size*.68);context.closePath();context.stroke();context.fill();
            if(['available','active'].includes(status)){context.fillStyle='#fff';context.font='bold 13px monospace';context.textAlign='center';context.fillText(`${point.name} · ${d.toFixed(1)} m`,x,horizon-size*1.95)}
        });
    }

    function drawPortals(fov,focal,horizon) {
        PORTALS.filter(portal=>portal.floor===player.floor).forEach(portal=>{
            const dx=portal.x-player.x,dy=portal.y-player.y,d=Math.hypot(dx,dy);let angle=Math.atan2(dy,dx)-player.heading;
            while(angle>Math.PI)angle-=Math.PI*2;while(angle<-Math.PI)angle+=Math.PI*2;
            if(Math.abs(angle)>fov*.54||d<.5)return;
            const obstruction=rayHit(player.heading+angle,d);if(obstruction&&obstruction.distance<d-.45)return;
            const x=canvas.width*(.5+angle/fov),height=Math.max(32,Math.min(130,focal*1.7/d)),width=height*.48;
            context.strokeStyle='#5ff';context.lineWidth=3;context.strokeRect(x-width/2,horizon-height*.55,width,height);
            context.fillStyle='rgba(30,220,220,.18)';context.fillRect(x-width/2,horizon-height*.55,width,height);
            if(d<5){context.fillStyle='#dfffff';context.font='bold 13px monospace';context.textAlign='center';context.fillText(`E · ${portal.label}`,x,horizon-height*.7)}
        });
    }

    function drawMinimap() {
        const size=178,left=canvas.width-size-12,top=12,scale=3.1,statuses=statusMap();
        context.save();context.beginPath();context.rect(left,top,size,size);context.clip();context.fillStyle='#071012dd';context.fillRect(left,top,size,size);
        const project=(x,y)=>[left+size/2+(x-player.x)*scale,top+size/2-(y-player.y)*scale];
        for(const room of ROOMS.filter(room=>room.floor===player.floor)){const [x1,y1]=project(room.x1,room.y2),[x2,y2]=project(room.x2,room.y1);context.fillStyle=room.color+'99';context.fillRect(x1,y1,x2-x1,y2-y1)}
        for(const wall of currentWalls()){const a=project(wall.x1,wall.y1),b=project(wall.x2,wall.y2);context.strokeStyle='#d4e2df';context.lineWidth=2;context.beginPath();context.moveTo(...a);context.lineTo(...b);context.stroke()}
        CHECKPOINTS.filter(point=>point.floor===player.floor).forEach(point=>{const [x,y]=project(point.x,point.y),status=statuses[point.id]||'locked';context.fillStyle=status==='complete'?'#0f8':['available','active'].includes(status)?'#ff0':'#58646a';context.beginPath();context.arc(x,y,4,0,Math.PI*2);context.fill()});
        PORTALS.filter(portal=>portal.floor===player.floor).forEach(portal=>{const [x,y]=project(portal.x,portal.y);context.fillStyle='#5ff';context.fillRect(x-4,y-4,8,8)});
        context.fillStyle='#dfffff';context.font='bold 11px monospace';context.textAlign='left';context.fillText(FLOOR_NAMES[player.floor],left+7,top+14);
        context.translate(left+size/2,top+size/2);context.rotate(-player.heading);context.fillStyle='#0ff';context.beginPath();context.moveTo(10,0);context.lineTo(-7,-6);context.lineTo(-7,6);context.closePath();context.fill();context.restore();context.strokeStyle='#0aa';context.strokeRect(left,top,size,size);
    }

    function updateHud() {
        const zone=ROOMS.find(room=>room.floor===player.floor&&player.x>=room.x1&&player.x<=room.x2&&player.y>=room.y1&&player.y<=room.y2)?.name||'SERVISNÍ KORIDOR';
        const target=activeCheckpoint(),targetNode=document.getElementById('chronos3d-target');
        const zoneNode=document.getElementById('chronos3d-zone');if(zoneNode)zoneNode.innerHTML=`${FLOOR_NAMES[player.floor]} · ZÓNA <strong>${zone}</strong>`;
        if(targetNode)targetNode.innerHTML=target?`CÍL <strong>${target.name} · ${target.floor===player.floor?`${localDistance(target).toFixed(1)} m`:FLOOR_NAMES[target.floor]}</strong>`:'CÍL <strong>ČEKÁ NA SYNCHRONIZACI</strong>';
    }

    function interact() {
        const target=activeCheckpoint(),message=document.getElementById('chronos3d-message');
        const portal=PORTALS.filter(item=>item.floor===player.floor).sort((a,b)=>localDistance(a)-localDistance(b))[0];
        if(portal&&localDistance(portal)<=2.8){player={x:portal.toX,y:portal.toY,floor:portal.to,heading:player.heading};if(message)message.textContent=`Přesun: ${FLOOR_NAMES[player.floor]}.`;messageUntil=performance.now()+1800;startLoop();return}
        if(!progress){if(message)message.textContent='Nejprve založte nebo obnovte herní relaci.';return}
        if(!target||target.floor!==player.floor||localDistance(target)>2.8){if(message)message.textContent='V dosahu není aktivní časová kotva.';messageUntil=performance.now()+1800;startLoop();return}
        if(typeof ws==='undefined'||!ws||ws.readyState!==WebSocket.OPEN){if(message)message.textContent='Backend není připojen.';return}
        ws.send(JSON.stringify({type:'qr.detected',payload:{value:`escapebot://checkpoint/${target.token}`}}));
        if(message)message.textContent=`Aktivuji: ${target.name}. Otevřete ARCHIV HÁDANEK.`;
        messageUntil=performance.now()+2600;startLoop();
    }

    function toggleLayer() {future=!future;const node=document.getElementById('chronos3d-layer');if(node)node.textContent=`VRSTVA ${future?'BUDOUCNOST':'PŘÍTOMNOST'}`;draw()}
    function resetPlayer(){player={x:0,y:19,floor:0,heading:-Math.PI/2};const node=document.getElementById('chronos3d-message');if(node)node.textContent='Pozice obnovena na recepci v přízemí.';draw()}
    function hexRgb(hex){const value=parseInt(hex.slice(1),16);return[(value>>16)&255,(value>>8)&255,value&255]}

    window.chronosWeb3D = {
        update(value) { progress=value; initialize(); const message=document.getElementById('chronos3d-message');if(message)message.textContent='Synchronizováno s týmovou relací.';draw(); },
        activate() { initialize(); active=true; canvas?.focus({preventScroll:true});startLoop(); },
    };
    window.addEventListener('DOMContentLoaded', initialize);
})();
