# Inventura administrátorských akcí Cloudflare

Stav k 29. září 2026 na větvi `feature/cf-05-event-admin`. Tento dokument je
zdrojem pravdy pro obnovu zásahů Game Mastera nad hádankami a minihrami. Neřeší
novou podobu autentizace administrátora.

## Stavové značky

- **hotovo** – Worker, klient i automatické testy mají použitelný kontrakt;
- **částečně** – část kontraktu existuje, ale některá akce nebo UI chybí;
- **chybí** – legacy implementace existuje, Cloudflare kontrakt nikoli;
- **nové** – funkce zatím neexistuje ani v legacy runtime.

## Matice akcí

| Priorita | Akce | Legacy backend | Cloudflare Worker | Současné UI | Výsledek inventury |
| --- | --- | --- | --- | --- | --- |
| 1 | Potvrdit nalezení checkpointu | `admin.checkpoint`, stav `found` | chybí | v Cloudflare režimu skryté | **chybí** – portovat validovaný a auditovaný přechod |
| 2 | Dokončit/přeskočit checkpoint | `admin.checkpoint`, stav `solved`, `penalty_preset` | chybí; overview neposílá presety | v Cloudflare režimu skryté | **chybí** – portovat přechod, odměny a právě jednu penalizaci |
| 3 | Restart celé aktivní minihry | `admin.game_reset` pro Kalibraci, Karla, Tři v řadě a Sokoban | chybí | v Cloudflare režimu skryté | **chybí** – resetovat pouze aktivní komponentu |
| 4 | Vyřadit hráče z týmové minihry | `admin.game_player: exclude` | autorizovaný `/api/admin/game-player`; jen Kalibrace a Tři v řadě | tlačítko je viditelné u podporovaných metrik | **hotovo**, ponechat jako regresní rozsah |
| 5 | Vrátit vyřazeného hráče | `admin.game_player: include` | endpoint akci odmítne | text odkazuje na obnovu spoluhráčem, tlačítko chybí | **částečně** – rozšířit existující kontrakt |
| 6 | Restartovat desku jednoho hráče | `admin.game_player: reset` | endpoint akci odmítne | tlačítko chybí | **částečně** – rozšířit existující kontrakt |
| 7 | Rezervovat hádanku volnému terminálu | `admin.terminal_reserve` | autorizovaný `/api/admin/terminal-reserve` | dostupné v záložce Terminály | **hotovo**, zachovat rezervaci zařízení oddělenou od týmu |
| 8 | Nastavit způsob hraní hádanky | `admin.scenario_play_modes` | chybí | formulář existuje, ale cloudová cesta neexistuje | **chybí** – portovat celý atomický dokument režimů |
| 9 | Nastavit globální katalog terminálů | `admin.terminal_catalog` | chybí | legacy formulář existuje | **chybí** – lze sloučit s nastavením způsobů hraní |
| 10 | Přidělit hádanku připojenému týmovému terminálu | `admin.terminal_assign` | přímý ekvivalent chybí; Worker používá rezervaci před převzetím | týmový panel je v Cloudflare režimu skrytý | **chybí / přehodnotit** – preferovat současný rezervační model |
| 11 | Uživatel explicitně opustí hru | neexistuje | neexistuje | chybí | **nové** – navržený kontrakt `lobby.leave` níže |

QR endpoint, prodloužení a ukončení relace, bodové úpravy, podpora, náhled
hráče, návratový QR, uzavření výsledku a řízený start nejsou blokátorem této
etapy. Musí ale zůstat v regresních testech.

## Povinný kontrakt Cloudflare akcí

Každý nový měnící endpoint musí:

1. ověřit `ADMIN_TOKEN` na veřejné Worker hranici;
2. přijmout validní `operation_id` a při opakování neprovést změnu podruhé;
3. ověřit relaci, scénář, cílový checkpoint/puzzle a povolený stavový přechod;
4. změnit stav v jedné serializované operaci Durable Objectu;
5. zapsat lidsky čitelný audit včetně času, cíle, předchozího a nového stavu;
6. odvysílat autoritativní `game.state` a `scenario.progress`, případně změnu
   skóre a zprávu týmu;
7. vrátit strukturovaný výsledek pro potvrzení v administračním UI.

`admin.overview` má nově poskytovat `admin_capabilities`. Klient podle něj
zobrazí jednotlivé akce; plošná podmínka `cloudflare_limited` nesmí být nadále
zdrojem pravdy. Minimální tvar:

```json
{
  "checkpoint_states": ["found", "solved"],
  "game_reset_adapters": ["line_game", "mine_karel", "triad", "sokoban"],
  "game_player_actions": ["exclude", "include", "reset"],
  "terminal_reservation": true,
  "scenario_play_modes": false
}
```

Legacy runtime má posílat stejný údaj, aby se klient nerozhodoval podle názvu
platformy.

## Nový hráčský kontrakt `lobby.leave`

Explicitní odchod není totéž co zavření stránky nebo ztráta spojení. Běžné
odpojení musí nadále zachovat identitu a umožnit `lobby.resume`.

Navržené chování:

- hráč odešle `lobby.leave` s jedinečným `operation_id`;
- server ověří, že identita socketu patří do relace, a odpoví `lobby.left`;
- klient odstraní `escapeBotLobby` až po přijetí potvrzení a vrátí se na výběr
  hry;
- `max_players`, již přidělené bodové úpravy, audit a historické výsledky hráče
  zůstanou zachované;
- pokud zbývají další hráči, zakladatelství přejde na nejdříve připojeného
  zbývajícího hráče;
- poslední hráč před startem rozpustí lobby a uvolní připojovací kód i frontu;
- odchod posledního hráče z rozehrané hry ji provozně ukončí jako opuštěnou;
- odchod během týmové Kalibrace nebo Tří v řadě nesmí sám dokončit checkpoint
  ani připsat týmový bonus; aktivní účast se přepočítá bez automatické odměny;
- akce vyžaduje výrazné potvrzení, protože je trvalá; pouhé dočasné odpojení
  zůstává doporučenou cestou pro pozdější návrat.

Terminál, administrátor a veřejná nástěnka nejsou hráči a `lobby.leave`
nepoužívají.

## Pořadí implementace po inventuře

1. Přidat `admin_capabilities` do obou runtime a otestovat jeho přesnost.
2. Portovat checkpoint `found` a `solved` včetně penalizačních presetů.
3. Portovat restart celé minihry.
4. Rozšířit hráčské akce o `include` a `reset`.
5. Přepnout administrační UI z `cloudflare_limited` na schopnosti serveru.
6. Doplnit režimy hraní a terminálový katalog; přímé přidělení řešit pouze
   tehdy, pokud nestačí existující rezervace.
7. Implementovat `lobby.leave` shodně v legacy i Cloudflare runtime.
8. Provést automatické testy, lokální vykreslený smoke test, staging a teprve
   potom produkční akceptaci.

