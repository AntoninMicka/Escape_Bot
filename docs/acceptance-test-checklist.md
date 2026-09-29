# Escape Bot – akceptační checklist

Tento checklist je určen k vytištění pro dokončení tří navazujících etap:
autentizovaný staging, produkční domény a živý test na více zařízeních.

## Záznam testu

| Údaj | Hodnota |
| --- | --- |
| Datum a čas |  |
| Tester / Game Master |  |
| Git commit |  |
| Staging Worker verze |  |
| Produkční Worker verze před nasazením |  |
| Produkční Worker verze po nasazení |  |
| Testovací event |  |
| Testovací tým |  |

Výsledek označte: **OK**, **CHYBA**, **NEPROVEDENO** nebo **NERELEVANTNÍ**.
Do produkce pokračujte pouze tehdy, když jsou všechny povinné stagingové body
OK a nejsou otevřené kritické chyby.

## 0. Příprava

- [ ] Pracovní strom je čistý: `git status --short` nic nevypíše.
- [ ] Je zaznamenán testovaný commit: `git rev-parse --short HEAD`.
- [ ] Kompletní kontrola prošla: `./run.sh check`.
- [ ] Staging `ADMIN_TOKEN` je dostupný testerovi, ale není napsán v checklistu,
      historii shellu, URL ani repozitáři.
- [ ] Pro test je založen samostatný event a testovací tým; nepoužívají se ostré
      výsledky účastníků.
- [ ] Je připraven notebook pro administraci a veřejnou nástěnku.
- [ ] Jsou připraveny alespoň tři telefony a jeden fyzický terminál/tablet.
- [ ] Zařízení mají nabitou baterii a známé připojení k testovací Wi-Fi.
- [ ] Je určen člověk, který může rozhodnout **GO / NO-GO** a případně provést
      návrat na předchozí verzi.

Poznámky:

______________________________________________________________________________

______________________________________________________________________________

## 1. Autentizovaný staging

Staging: `https://escape-bot-cf-staging.prijimaci-vycvik.workers.dev`

### 1.1 Základní dostupnost a přihlášení

- [ ] `/api/health` vrací stav `ok`, runtime `cloudflare` a prostředí `staging`.
- [ ] Načtou se `/`, `/admin`, `/display` a `/terminal` bez chybějících assetů.
- [ ] Administrace bez tokenu nezobrazí chráněná data ani neumožní měnící akci.
- [ ] Správný token načte přehled týmů a serverem oznámené schopnosti.
- [ ] Chybný token je odmítnut a nezmění žádný stav.
- [ ] Po obnovení stránky lze administraci znovu bezpečně načíst.

### 1.2 Event a řízené lobby

- [ ] Aktivovat testovací event a zapnout řízený režim.
- [ ] Z administrace založit prázdný tým.
- [ ] U týmu se zobrazí připojovací kód a čitelný QR kód.
- [ ] QR z telefonu otevře správnou staging doménu a připojí prvního hráče.
- [ ] První připojený hráč se stane zakladatelem týmu.
- [ ] Opakování stejné operace nevytvoří druhý tým.
- [ ] Tlačítko běžného startu respektuje minimální rozestup, kapacitu a provozní
      okno.
- [ ] Vynucený start obejde pouze minimální rozestup.
- [ ] Vynucený start neobejde kapacitu, uzavřené provozní okno ani globální stop.
- [ ] Odstranění týmu vyžaduje potvrzení.
- [ ] Odstraněný tým zmizí z přehledu a starý připojovací kód už nelze použít.
- [ ] Opakování stejného odstranění neprovede vedlejší účinky podruhé.

### 1.3 Zásahy nad checkpointy a minihrami

- [ ] Potvrdit nalezení checkpointu (`found`).
- [ ] Dokončit nebo přeskočit checkpoint (`solved`) se zvolenou penalizací.
- [ ] Ověřit, že se změna zobrazí současně hráčům i administraci.
- [ ] Restartovat celou aktivní Kalibraci.
- [ ] Restartovat celého Karla v minovém poli.
- [ ] Restartovat celé Tři v řadě.
- [ ] Restartovat celý Sokoban.
- [ ] U podporované týmové minihry vyřadit jednoho hráče.
- [ ] Vyřazeného hráče vrátit.
- [ ] Restartovat pouze desku jednoho hráče.
- [ ] Nepodporované akce nejsou zobrazeny.
- [ ] Každá měnící akce má potvrzení, jednoznačný výsledek a auditní záznam.

### 1.4 Podpora, terminály a výsledky

- [ ] Odeslat týmu zprávu podpory; zpráva dorazí právě jednou.
- [ ] Otevřít spectator pohled online hráče.
- [ ] Otevřít spectator pohled registrovaného offline hráče.
- [ ] Nastavit způsob hraní hádanky a po obnovení stránky ověřit jeho zachování.
- [ ] Upravit globální katalog terminálů bez vzniku druhého zdroje konfigurace.
- [ ] Rezervovat hádanku volnému terminálu.
- [ ] Ověřit, že rezervace zařízení nezmění členství hráčů v týmu.
- [ ] Ručně ukončený tým explicitně vyhodnotit.
- [ ] Výsledek se v žebříčku zapíše jen jednou.

### 1.5 Odchod hráče a obnova spojení

- [ ] Zavření stránky bez volby „opustit“ zachová možnost návratu přes resume.
- [ ] Odchod jednoho člena týmu zachová relaci v režimu `team`.
- [ ] Historické jméno a příspěvek odchozího hráče zůstanou pro výsledky.
- [ ] Zakladatelství přejde na nejdříve připojeného aktivního hráče.
- [ ] Odchod posledního aktivního člena týmovou hru ukončí.
- [ ] Odchod jednotlivce jeho hru ukončí.
- [ ] Odchod během týmové minihry sám nedokončí checkpoint ani nepřidá bonus.
- [ ] Návratový QR bezpečně přenese identitu na nové zařízení a staré odpojí.

### 1.6 Stagingová brána

- [ ] Konzole prohlížeče neobsahuje neočekávané chyby.
- [ ] QR endpoint vrací obrázek a zakazuje nevhodně velký nebo neplatný vstup.
- [ ] Po uspání a probuzení telefonu se obnoví autoritativní stav.
- [ ] Po ztrátě a návratu Wi-Fi se klient znovu připojí bez duplikace hráče.
- [ ] Kritické chyby: **0**.
- [ ] Závažné nevyřešené chyby: **0**.
- [ ] Rozhodnutí stagingu: **GO / NO-GO**.

Podpis testera: ________________________  Čas: ________________________

## 2. Produkční nasazení a domény

Produkční kanonická doména: `https://escape.proofofidea.cz`

Aliasy:

- `https://escape.antoninmicka.cz`
- `https://escape.tonymicka.cz`

### 2.1 Produkční preflight

- [ ] Stagingová brána má výsledek **GO**.
- [ ] Produkční `ADMIN_TOKEN` je nastaven bezpečným příkazem
      `./run.sh admin-token cloudflare production`; token není argument příkazu.
- [ ] Produkční dry-run prošel:
      `./run.sh deploy cloudflare production --dry-run`.
- [ ] Pracovní strom je stále čistý.
- [ ] Je zaznamenána dosavadní produkční verze a připraven postup návratu.
- [ ] Game Master a tester vědí o plánovaném okně nasazení.
- [ ] V době nasazení neběží ostrá hra, nebo je výslovně schválen test přežití
      deploye rozehrané relace.

### 2.2 Nasazení

- [ ] Spustit `./run.sh deploy cloudflare production` a potvrdit slovem `DEPLOY`.
- [ ] Zaznamenat nové Worker Version ID do záhlaví checklistu.
- [ ] Worker startuje bez chyby a bindingy Durable Objectů jsou dostupné.
- [ ] Krátce sledovat logy: `./run.sh tail cloudflare production`.

### 2.3 DNS, HTTPS a směrování

- [ ] `escape.proofofidea.cz` má platný důvěryhodný certifikát.
- [ ] Kanonická doména zachová cestu a query parametry.
- [ ] `escape.antoninmicka.cz` přesměruje stavem 308 na kanonickou doménu.
- [ ] `escape.tonymicka.cz` přesměruje stavem 308 na kanonickou doménu.
- [ ] Přesměrování zachová například `/admin`, `/terminal` a `?join=...`.
- [ ] Na kanonické doméně fungují `/`, `/admin`, `/display` a `/terminal`.
- [ ] `/api/health` hlásí prostředí `production`.
- [ ] `/api/qr` vrací QR pro kanonickou produkční URL.
- [ ] WebSocket připojení funguje přes `wss://` bez mixed-content chyby.

### 2.4 Minimální produkční smoke test

- [ ] Použít pouze jasně označený testovací event a testovací tým.
- [ ] Přihlásit administraci produkčním tokenem.
- [ ] Založit testovací tým a připojit telefon přes QR.
- [ ] Ověřit změnu checkpointu a restart jedné minihry.
- [ ] Ověřit reconnect telefonu.
- [ ] Testovací tým odstranit a ověřit neplatnost jeho starého kódu.
- [ ] Produkční log neobsahuje neočekávané výjimky.
- [ ] Rozhodnutí produkce: **GO / ROLLBACK**.

Podpis odpovědné osoby: ________________________  Čas: ________________________

## 3. Živá akceptace na více zařízeních

### 3.1 Evidence zařízení

| Zařízení | Model / OS / prohlížeč | Role | Výsledek |
| --- | --- | --- | --- |
| Telefon 1 |  | Zakladatel |  |
| Telefon 2 |  | Člen týmu |  |
| Telefon 3 |  | Člen týmu / obnova |  |
| Terminál 1 |  | Vyhrazená minihra |  |
| Notebook |  | Admin / nástěnka |  |

### 3.2 Kompletní týmový průchod

- [ ] Tři hráči se připojí do stejného týmu, nikoli do tří relací.
- [ ] Každý vidí správné jméno, roli a týmový postup.
- [ ] Soukromé desky Kalibrace a Tří v řadě se mezi hráči nezamění.
- [ ] Sdílené minihry mají shodný autoritativní stav na všech zařízeních.
- [ ] Opakovaný QR nezpůsobí dvojí zápis checkpointu ani bodů.
- [ ] Dva téměř současné povely nezpůsobí rozpad stavu.
- [ ] Celou hru lze dokončit bez zásahu autora, není-li skutečná provozní závada.
- [ ] Finále se otevře až po splnění požadované trasy a inventáře.
- [ ] Výsledek obsahuje všechny historické členy týmu právě jednou.

### 3.3 Síť, uspání a obnova

- [ ] Telefon 1 uspat alespoň na dvě minuty a poté obnovit.
- [ ] Telefon 2 odpojit od Wi-Fi a znovu připojit.
- [ ] Telefon 3 zavřít bez explicitního odchodu a obnovit relaci.
- [ ] Žádný z kroků nevytvoří duplicitního hráče.
- [ ] Chat, checkpointy, skóre a minihry zůstanou zachované.
- [ ] Pokud je schválen test deploye/restartu, rozehraná relace se po něm obnoví.

### 3.4 Terminál

- [ ] Terminál se zaregistruje jako zařízení, nikoli jako hráč nebo tým.
- [ ] Rezervovaný terminál převezme pouze správný tým.
- [ ] Přidělená minihra se zobrazí až po autoritativním stavu serveru.
- [ ] Reset minihry vyčistí staré lokální zobrazení terminálu.
- [ ] Dokončení, odpojení nebo nová registrace terminál bezpečně uvolní.
- [ ] Rezervace zařízení zůstane podle očekávaného provozního modelu zachována.

### 3.5 Administrátorský zásah během hry

- [ ] Game Master identifikuje správný tým a hráče.
- [ ] Odešle podporu a tým ji přijme právě jednou.
- [ ] Provede technický skip checkpointu se správnou penalizací.
- [ ] Restartuje aktivní minihru a zařízení zobrazí nový stav.
- [ ] Vyřadí a následně vrátí hráče u podporované minihry.
- [ ] Obnoví identitu hráče na novém telefonu.
- [ ] Globální stop ukončí aktivní hry a zruší startovní rezervace.
- [ ] Ručně ukončený výsledek se zapíše až po explicitním vyhodnocení.

### 3.6 Použitelnost a fyzické podmínky

- [ ] Text je čitelný na nejmenším telefonu a ve venkovním světle.
- [ ] Ovládání hlavních kroků je možné jednou rukou.
- [ ] Zvuk, mute, hlasitost, titulky a opakování replik fungují.
- [ ] Z každé obrazovky existuje bezpečný návrat bez ztráty hry.
- [ ] QR lze načíst na všech testovaných telefonech.
- [ ] Týmy se při plánovaném rozestupu nepotkávají u úzkých stanovišť.
- [ ] Nouzová vnitřní varianta trasy je použitelná.

## 4. Záznam nalezených chyb

| ID | Čas | Zařízení / tým | Kroky | Očekávání | Skutečnost | Závažnost |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

Závažnost:

- **Kritická:** ztráta nebo smíchání stavu, neautorizovaný zásah, nefunkční
  start či dokončení hry, nefunkční rollback.
- **Závažná:** hlavní herní nebo správcovský krok nemá bezpečnou náhradní cestu.
- **Střední:** krok má použitelnou náhradní cestu, ale narušuje provoz.
- **Drobná:** kosmetická nebo textová závada bez dopadu na průchod.

## 5. Závěrečné rozhodnutí

- [ ] Všechny kritické body jsou **OK**.
- [ ] Nezůstala žádná kritická nebo závažná nevyřešená chyba.
- [ ] Všechny neprovedené body mají zapsaný důvod a vlastníka.
- [ ] Testovací data jsou oddělena od ostrých výsledků.
- [ ] Game Master zná nouzový postup a kontaktní osobu.
- [ ] Výsledek: **GO / PODMÍNĚNÉ GO / NO-GO / ROLLBACK**.

Shrnutí a podmínky:

______________________________________________________________________________

______________________________________________________________________________

______________________________________________________________________________

Tester: ______________________________  Podpis: ______________________________

Game Master: _________________________  Podpis: ______________________________

Odpovědná osoba: _____________________  Podpis: ______________________________
