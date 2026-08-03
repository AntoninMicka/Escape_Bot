# Escape Bot Desktop

Desktop wrapper automaticky spustí backend Escape Botu, přihlásí lokální webovou administraci v nativním Qt okně a umí na podporovaném počítači vytvořit lokální Wi-Fi AP.

## Podpora

- Linux: detekce Wi-Fi a vytvoření AP přes NetworkManager/`nmcli`.
- Windows a macOS: Qt detekuje aktivní Wi-Fi rozhraní, vytvoření AP zatím není implementováno, protože vyžaduje samostatný privilegovaný systémový adaptér.
- Admin: výchozí adresa je `https://localhost:8088/admin`; lze zadat i backend na jiném lokálním uzlu.
- Backend: wrapper najde kořen projektu, použije `backend/.venv` a spustí `python -m escape_bot.server`.
- Přihlášení: pro každý běh vygeneruje nový náhodný admin token, předá jej backendu přes prostředí procesu a vloží do `sessionStorage` pouze pro localhost.

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
