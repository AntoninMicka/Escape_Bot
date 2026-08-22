# Escape Bot Desktop

Repozitář sestavuje dvě oddělené Qt aplikace. `EscapeBotDesktop` je lokální, výhradně souborová varianta. `EscapeBotCloudOperator` žádný lokální backend nespouští a slouží k řízení krátkodobého nasazení na Google Cloud.

## Cloud Operator

Cloud Operator spojuje konfiguraci prostředí, Terraform provisioning, vytvoření tajemství, deploy image podle digestu, pauzu/obnovení, archivaci, reset, stažení archivů a finální odstranění infrastruktury. Běžný provoz nabízí jako několik složených tlačítek; jednotlivé kroky zůstávají v pokročilé části.

Tlačítko **Přihlásit Google účet** spustí jediný webový `gcloud auth login --update-adc`, který připraví zároveň Google Cloud CLI i Application Default Credentials pro Terraform. **Připravit testovací prostředí** automaticky vytvoří infrastrukturu, náhodný admin token v Secret Manageru, restartuje VM, počká na konfiguraci a nasadí image. Short-run používá atomické JSON soubory na samostatném perzistentním disku, takže nevytváří Cloud SQL, databázové heslo ani proxy. Hodnota admin tokenu se nezapisuje do logu ani do nastavení aplikace.

V pravé části je vzdálený `/admin` dashboard. Operátor načte admin token ze Secret Manageru do paměti a vloží jej pouze do `sessionStorage` HTTPS dashboardu. Token nevkládá do URL, logu ani `QSettings`; nedůvěryhodný TLS certifikát nepovolí.

Vyžaduje příkazy `bash`, `gcloud`, `terraform` a `docker` a aktivní přihlášení do Google Cloud. Je určen pro Linux/macOS administrátorskou stanici. Konfiguraci prostředí ukládá přes Qt `QSettings`, nikoli cloudová hesla nebo tokeny.

### Převzetí na jiném počítači

Terraform state je v GCS bucketu navrženém jako `<project-id>-escape-bot-tfstate`; bucket má jednotná oprávnění, zákaz veřejného přístupu a verzování. Operátor do něj vedle state ukládá netajný `short-run.tfvars`. Případný starší lokální state se při prvním provisioningu migruje do GCS.

Na novém počítači naklonujte stejnou verzi repozitáře a přihlaste Google účet. Tlačítko **Vyhledat a převzít projekt** zobrazí aktivní projekty dostupné účtu, v projektu vyhledá state buckety Escape Botu a nabídne nalezená short-run prostředí. Po výběru stáhne sdílený `tfvars`, vybere vzdálený workspace a doplní hodnoty z Terraform outputs. Poté lze provádět deploy, pauzu, archivaci, reset i finální destroy. Účet musí mít odpovídající projektová, Secret Manager, IAP/OS Login a GCS oprávnění.

Pro ruční převzetí lze nadále vyplnit projekt, prostředí a state bucket a použít **Načíst existující prostředí**. Projekt bez existujícího state bucketu průvodce převede do režimu nového nasazení a navrhne mu výchozí hodnoty.

Tlačítko **Navrhnout povinné hodnoty** načte aktivní GCP projekt a odvodí bezpečné výchozí názvy prostředí, VM, state bucketu, regionu, zóny a lokálních cest. Doménu a neměnný image digest musí uživatel dodat; před provisioningem z nich operátor atomicky vytvoří netajný `short-run.tfvars`.

### Fáze životního cyklu

Aktuální projekt zobrazuje sdílenou fázi prostředí, počet úspěšných deployů, počet připravených ostrých běhů a archivů. Stav a posledních 50 událostí se ukládají do `operator-state/<environment>.json` ve state bucketu, takže jsou stejné na všech počítačích. Opakovaný deploy opravy pouze zvýší revizi a zachová fázi; každé úspěšné **Připravit ostrý provoz** zvýší číslo ostrého běhu. Pozastavení si pamatuje předchozí fázi a po obnovení se do ní vrátí.

Hlavní tlačítka se aktivují podle načtené fáze. Nové nebo odstraněné prostředí nabízí přípravu, testovací a připravené prostředí nabízí opakované opravy i ostré běhy a pozastavené prostředí pouze obnovení. Po dobu operace jsou další mutační akce zamčené. Pokročilá sekce zůstává dostupná jako vědomá nouzová cesta; zakázaná tlačítka mají vysvětlující tooltip.

```bash
cmake -S desktop -B desktop/build
cmake --build desktop/build --target EscapeBotCloudOperator
./desktop/build/EscapeBotCloudOperator
```

Před destrukcí vyžaduje lokálně stažený archiv s `archive-report.json`; reset a odstranění infrastruktury navíc vyžadují opsání potvrzovací fráze.

Desktop wrapper automaticky spustí backend Escape Botu, přihlásí lokální webovou administraci v nativním Qt okně a umí na podporovaném počítači vytvořit lokální Wi-Fi AP.

## Podpora

- Linux: detekce Wi-Fi a vytvoření AP přes NetworkManager/`nmcli`.
- Windows a macOS: Qt detekuje aktivní Wi-Fi rozhraní, vytvoření AP zatím není implementováno, protože vyžaduje samostatný privilegovaný systémový adaptér.
- Admin: výchozí adresa je `https://localhost:8088/admin`; lze zadat i backend na jiném lokálním uzlu.
- Backend: wrapper najde kořen projektu, použije `backend/.venv` a spustí `python -m escape_bot.server`.
- Persistence: desktopová varianta vždy vynutí `JsonStorage` a ukládá do souborů v `backend/`. Ignoruje zděděné cloudové nastavení PostgreSQL a databázovou URL backendu nepředává.
- Přihlášení: pro každý běh vygeneruje nový náhodný admin token, předá jej backendu přes prostředí procesu a vloží do `sessionStorage` pouze pro localhost.
- Captive portál: po spuštění AP aktivuje lokální DNS/HTTP responder a přesměruje běžné HTTP captive sondy na hru.

Wrapper ignoruje chybu TLS certifikátu pouze pro `localhost`, `127.0.0.1` a `::1`. Pro vzdálenou adresu vyžaduje důvěryhodný certifikát. Heslo hotspotu se neukládá do nastavení wrapperu; NetworkManager je uloží do svého chráněného systémového profilu připojení.

## Sestavení na Linuxu

Požadavky: CMake, kompilátor s C++20, Qt 6.5+ s moduly Core, Network, Widgets a WebEngineWidgets a NetworkManager s `nmcli`.

Na Ubuntu/Debian odpovídá vloženému prohlížeči balíček `qt6-webengine-dev`. Je to systémová závislost a projekt ji sám neinstaluje.

```bash
cmake -S desktop -B desktop/build
cmake --build desktop/build
./desktop/build/EscapeBotDesktop
```

Backend se spustí automaticky a po ukončení wrapperu se také zastaví. Pokud virtuální prostředí ještě neexistuje, připravte je jednou pomocí `./start_backend.sh`, proces ukončete a poté spusťte wrapper. Systémový Python lze použít jako fallback, musí však mít nainstalované závislosti z `backend/requirements.txt`.

Automatické přihlášení se z bezpečnostních důvodů provede pouze pro `localhost`, `127.0.0.1` nebo `::1`. Pro vzdálený backend je nutné zadat jeho administrační heslo ručně. Token se nevkládá do URL, argumentů procesu ani nastavení wrapperu.

## Síťová oprávnění

Vytvoření AP mění systémové síťové připojení. NetworkManager proto může zobrazit Polkit dialog nebo operaci zamítnout. Wrapper nikdy nespouštějte celý jako root. Produkční počítač má dostat omezené Polkit pravidlo pouze pro obsluhu NetworkManageru, nikoli obecná administrátorská práva.

Příkaz vytváří připojení se jménem `EscapeBot-AP`. Tlačítko **Zastavit AP** ukončuje pouze toto pojmenované připojení.

Jedna Wi-Fi karta obvykle nemůže současně udržovat běžné Wi-Fi připojení a spolehlivý AP. Wrapper proto může při spuštění hotspotu odpojit dosavadní bezdrátový uplink. Pro internetový uplink použijte ethernet, LTE nebo druhý adaptér. NetworkManager ve výchozím hotspot režimu zajišťuje lokální DHCP, DNS forwarding a NAT; produkční captive portal a CAPPORT podle infrastrukturního návrhu jsou samostatná navazující služba.

### Captive portál

Wrapper spouští neprivilegovaný DNS responder na portu 1053 a HTTP responder na portu 8091. Port 1053 je zvolen záměrně, aby nekolidoval s mDNS/Avahi na portu 5353. Pomocný skript přes Polkit vytvoří samostatnou tabulku `inet escapebot_captive` v nftables a pouze na rozhraní AP přesměruje DNS a port 80 na tyto služby. Při zastavení AP tabulku odstraní; ostatních firewallových pravidel se nedotýká.

Výchozí brána hotspotu je `10.42.0.1` a cílem portálu je `https://10.42.0.1:8088/`. Připojené telefony proto otevřou hru, jakmile provedou běžnou HTTP kontrolu captive sítě. Pro zařízení hráčů musí být produkční backend opatřen certifikátem, kterému telefon důvěřuje a který obsahuje použitou doménu. Wrapper nepodvrhuje HTTPS provoz; vývojový certifikát pro localhost není na cizím telefonu dostačující.

Toto je kompatibilní legacy captive flow. Standardní CAPPORT přes RFC 8908/8910 zůstává doporučeným produkčním rozšířením, protože jeho DHCP option 114 musí poskytovat DHCP služba konkrétní cílové infrastruktury.
