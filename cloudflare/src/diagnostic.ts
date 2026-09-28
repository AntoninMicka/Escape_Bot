export function diagnosticPage(): Response {
  const html = `<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Escape Bot · Cloudflare CF-01</title>
  <style>
    :root{color-scheme:dark;font-family:system-ui,sans-serif;background:#06161a;color:#dffcff}
    body{max-width:900px;margin:0 auto;padding:24px}h1{color:#65f7ff}p{line-height:1.5}
    .panel{padding:18px;border:1px solid #28636a;border-radius:14px;background:#0a2227;margin:16px 0}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
    label{display:grid;gap:6px;color:#9bc6ca}input,button{font:inherit;padding:10px 12px;border-radius:8px}
    input{border:1px solid #28636a;background:#041216;color:#fff}button{border:1px solid #65f7ff;background:#103b42;color:#fff;cursor:pointer}
    button:disabled{opacity:.45;cursor:not-allowed}.status{font-weight:700}.online{color:#72f59d}.offline{color:#ff9b91}
    pre{min-height:260px;max-height:55vh;overflow:auto;white-space:pre-wrap;background:#020b0d;padding:14px;border-radius:10px}
    code{color:#9ef8ff}
  </style>
</head>
<body>
  <h1>Escape Bot · Cloudflare CF-01</h1>
  <p>Diagnostika samostatného Workeru a <code>GameSession</code> Durable Objectu. Otevřením stejného session ID ve více kartách lze ověřit broadcast.</p>
  <section class="panel grid">
    <label>Session ID<input id="session" autocomplete="off"></label>
    <label>Client ID<input id="client" autocomplete="off"></label>
  </section>
  <section class="panel">
    <p id="status" class="status offline">● ODPOJENO</p>
    <div class="grid">
      <button id="connect">Připojit</button>
      <button data-action="resume" disabled>Vyžádat resume</button>
      <button data-action="broadcast" disabled>Broadcast</button>
      <button data-action="state" disabled>Nastavit testovací skóre</button>
      <button data-action="deadline" disabled>Deadline za 1 sekundu</button>
      <button id="clear">Vyčistit log</button>
    </div>
  </section>
  <pre id="log" aria-live="polite"></pre>
  <script>
    const sessionInput=document.getElementById('session');
    const clientInput=document.getElementById('client');
    const status=document.getElementById('status');
    const log=document.getElementById('log');
    const actionButtons=[...document.querySelectorAll('[data-action]')];
    sessionInput.value=localStorage.getItem('cf-spike-session')||crypto.randomUUID();
    clientInput.value='browser-'+crypto.randomUUID().slice(0,8);
    let socket=null;
    function write(direction,value){
      const line=typeof value==='string'?value:JSON.stringify(value,null,2);
      log.textContent+='['+new Date().toLocaleTimeString()+'] '+direction+' '+line+'\\n';
      log.scrollTop=log.scrollHeight;
    }
    function send(type,payload={}){
      const message={type,payload};
      if(!socket||socket.readyState!==WebSocket.OPEN){write('!', 'WebSocket není připojený.');return}
      socket.send(JSON.stringify(message));write('→',message);
    }
    function setConnected(connected){
      status.textContent=connected?'● PŘIPOJENO':'● ODPOJENO';
      status.className='status '+(connected?'online':'offline');
      actionButtons.forEach(button=>button.disabled=!connected);
    }
    document.getElementById('connect').onclick=()=>{
      socket?.close(1000,'reconnect');
      const sessionId=sessionInput.value.trim();
      const clientId=clientInput.value.trim();
      localStorage.setItem('cf-spike-session',sessionId);
      const protocol=location.protocol==='https:'?'wss:':'ws:';
      const url=protocol+'//'+location.host+'/ws?session_id='+encodeURIComponent(sessionId)+'&client_id='+encodeURIComponent(clientId);
      write('·','Připojuji '+url);
      socket=new WebSocket(url);
      socket.onopen=()=>setConnected(true);
      socket.onmessage=event=>{try{write('←',JSON.parse(event.data))}catch{write('←',event.data)}};
      socket.onerror=()=>write('!','WebSocket chyba');
      socket.onclose=event=>{setConnected(false);write('·','Spojení ukončeno: '+event.code+' '+event.reason)};
    };
    document.querySelector('[data-action="resume"]').onclick=()=>send('lobby.resume');
    document.querySelector('[data-action="broadcast"]').onclick=()=>send('spike.broadcast',{text:'Pozdrav z '+clientInput.value});
    document.querySelector('[data-action="state"]').onclick=()=>send('spike.state.patch',{phase:'operations',score:Math.floor(Math.random()*1000)});
    document.querySelector('[data-action="deadline"]').onclick=()=>send('spike.deadline.schedule',{deadline_at:Date.now()+1000});
    document.getElementById('clear').onclick=()=>{log.textContent=''};
  </script>
</body>
</html>`;
  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "Content-Security-Policy":
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self' wss: ws:; base-uri 'none'; frame-ancestors 'none'",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
