# Postup migrace Escape Botu na cloud

## Cílová architektura

Webová PWA zůstane statickým klientem. FastAPI bude obsluhovat HTTPS API a WSS spojení, PostgreSQL převezme veškerý trvalý stav a cloudový secret manager administrační a databázová hesla. Povinný herní průchod nesmí záviset na Ollamě ani ComfyUI; případné AI funkce zůstanou vypnutelným doplňkem.

## 1. Stabilizace před migrací

1. Zmrazit formát scénáře a dokončit deterministické nápovědy, odpovědi a minihry.
2. Sepsat konfiguraci prostředí: databázové URL, veřejná URL, admin token, demo režim a úroveň logování.
3. Přidat produkční health endpoint ověřující aplikaci i databázi.
4. Kontejnerizovat backend a klientská aktiva, spouštět ASGI server bez vývojového reloadu.

## 2. Přesun persistence

1. Navrhnout tabulky pro relace, lobby, hráče, leaderboard, runtime nastavení a auditní události.
2. Ukládat herní snapshot jako verzovaný JSONB, ale identitu relací, skóre, časy a vazby hráčů držet v samostatných sloupcích.
3. Zavést databázové migrace a transakce; souběžnou změnu jedné relace chránit verzí záznamu nebo zámkem.
4. Napsat jednorázový import stávajících JSON souborů a validační report počtů a vazeb.
5. Zapnout automatické zálohy a nacvičit obnovu do oddělené databáze.

## 3. První cloudové nasazení

1. Vytvořit staging se spravovaným PostgreSQL, trvalým HTTPS/WSS a stejnou časovou zónou aplikace v UTC.
2. Pro první verzi použít jednu aplikační instanci. Současná evidence WebSocketů je procesní a bez další vrstvy není bezpečná pro více instancí.
3. Nastavit důvěryhodný reverse proxy/load balancer, bezpečnostní hlavičky, omezení velikosti zpráv a rate limiting přihlášení do administrace.
4. Přidat strukturované logy, sledování výjimek, latence WebSocketů, počtu spojení a stavu databázového poolu.

## 4. Testování a přepnutí

1. Na stagingu projít sólo hru i tým se třemi telefony, uspání zařízení, reconnect a restart aplikační instance.
2. Spustit více paralelních týmů a ověřit izolaci relací, souběžné povely, nápovědy, admin zásahy a Síň slávy.
3. Importovat kopii lokálních dat a porovnat počty lobby, hráčů, relací a výsledků.
4. Připravit rollback na předchozí image a export databáze před přepnutím.
5. Snížit DNS TTL, provést finální import v krátkém servisním okně a přepnout DNS až po smoke testu.

## 5. Pozdější horizontální škálování

Více aplikačních instancí vyžaduje Redis pub/sub nebo obdobný message broker pro týmové broadcasty, sdílenou evidenci přítomnosti, distribuované zámky nad změnami relace a idempotentní zpracování zpráv. Do té doby musí load balancer držet jednu instanci; sticky sessions samy neřeší broadcast ani konzistenci.
