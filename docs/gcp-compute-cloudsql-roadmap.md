# Roadmap: Google Compute Engine + Cloud SQL

## Cíl

Provozovat Escape Bot na jedné instanci Google Compute Engine s důvěryhodným HTTPS/WSS, automatickým dohledem a databází Cloud SQL for PostgreSQL. První produkční verze zůstane záměrně single-instance. Více aplikačních replik přijde až po zavedení sdíleného WebSocket broadcastu a distribuovaných zámků.

## Cílová architektura

```text
Cloud DNS
   │
Google Cloud Firewall
   │
statická veřejná IP
   │
Compute Engine e2-medium · europe-central2
├── Caddy · HTTPS/WSS
├── Escape Bot · Docker Compose · 1 worker
├── Ops Agent
└── Cloud SQL Auth Proxy / Cloud SQL Connector
            │
            └── Cloud SQL PostgreSQL
                ├── automatické zálohy + PITR
                └── privátní IP

Secret Manager ── admin token a databázová tajemství
Cloud Monitoring ── healthchecky, logy a alerty
Cloud Storage ── exporty před releasem a dlouhodobé zálohy
```

## Zásady migrace

- Povinný herní průchod nesmí záviset na externí AI službě.
- Produkce poběží s jedním workerem a jednou aplikační instancí.
- PostgreSQL se zavede nejprve ve vývojovém a staging prostředí.
- JSON soubory zůstanou po omezenou dobu dostupné jako exportní a rollback formát.
- Každá databázová změna musí mít dopřednou migraci, ověření a popsaný rollback.
- Časy se v databázi ukládají v UTC; provozní plán používá nastavenou IANA časovou zónu.
- Přepnutí produkce proběhne v servisním okně po finálním exportu JSON dat.

## Fáze 0 – rozhodnutí a účty

Odhad: 0,5–1 den.

1. Zvolit GCP projekt pro produkci a samostatný projekt pro staging.
2. Nastavit billing budget a upozornění na 50 %, 80 % a 100 % rozpočtu.
3. Zvolit doménu a region `europe-central2` (Varšava); případně `europe-west3` (Frankfurt).
4. Určit RPO a RTO:
   - doporučené RPO: nejvýše 15 minut,
   - doporučené RTO: nejvýše 60 minut.
5. Určit dobu uchování lobby, auditních událostí a výsledků.

Výstup: schválený region, rozpočet, doména, RPO/RTO a retenční pravidla.

## Fáze 1 – Compute Engine staging bez změny persistence

Odhad: 1–2 dny.

1. Vytvořit VM `e2-medium`, Ubuntu 24.04 LTS, Balanced Persistent Disk 30–50 GB.
2. Rezervovat statickou IP a připojit DNS staging domény.
3. Povolit ingress pouze TCP 80 a 443; SSH řešit přes IAP nebo omezenou správcovskou IP.
4. Nainstalovat Docker Engine, Compose plugin a Google Ops Agent.
5. Uložit administrační token do Secret Manageru a při deployi ho předat jako proměnnou prostředí.
6. Nasadit současný `compose.cloud.yml`; datový adresář držet na Persistent Disku.
7. Zapnout denní snapshot policy disku.
8. Přidat uptime check na `/api/health` a alerty pro nedostupnost, vysoké využití disku, RAM a restart kontejneru.

Akceptace:

- HTTPS a WSS fungují z telefonu bez varování certifikátu.
- Sólo a tříčlenný tým dokončí celý průchod.
- Reconnect telefonu a restart kontejneru obnoví relaci.
- Restart VM zachová data.
- Admin rozhraní není dostupné bez tokenu.
- Snapshot lze obnovit na testovací VM.

Rollback: vrátit předchozí Docker image a Persistent Disk ze snapshotu.

## Fáze 2 – databázová vrstva v aplikaci

Odhad: 3–5 dní.

1. Zavést rozhraní úložiště oddělené od `server.py`, například:

```text
Storage
├── load_sessions / save_session
├── load_lobbies / save_lobby
├── load_runtime_settings / save_runtime_settings
├── load_leaderboard / save_leaderboard_entry
└── append_audit_event
```

2. Zachovat `JsonStorage` pro lokální a nouzový režim.
3. Doplnit `PostgresStorage` s connection poolem a transakcemi.
4. Přidat Alembic nebo ekvivalentní verzované databázové migrace.
5. Přidat `schema_version` do snapshotu herní relace.
6. Chránit souběžné změny relace optimistickou verzí nebo `SELECT … FOR UPDATE`.
7. Zapisovat jednu herní zprávu a související skóre/checkpoint v jedné transakci.
8. Doplnit idempotency klíč pro operace, které přičítají body nebo uzavírají checkpoint.

Navržené tabulky:

| Tabulka | Hlavní obsah |
|---|---|
| `game_sessions` | ID, fáze, skóre, stav JSONB, verze, začátek a konec |
| `lobbies` | režim, název, join code, creator, stav startu |
| `players` | identita hráče, lobby, jméno a časy připojení |
| `leaderboard_entries` | tým, skóre, dokončení a způsob vyhodnocení |
| `runtime_settings` | verzovaná globální provozní konfigurace |
| `audit_events` | append-only události hráčů a administrace |
| `schema_migrations` | verze databázového schématu |

Akceptace:

- Celý testovací scénář prochází nad JSON i PostgreSQL implementací.
- Dvě souběžné zprávy stejné relace nezpůsobí dvojí body.
- Přerušení databázového spojení vrátí řízenou chybu a po reconnectu pokračuje.
- Health endpoint rozlišuje `live` a `ready`; readiness kontroluje databázi.

Rollback: přepnout `ESCAPEBOT_STORAGE_BACKEND=json` a použít poslední konzistentní export.

## Fáze 3 – Cloud SQL staging

Odhad: 1–2 dny.

1. Vytvořit Cloud SQL for PostgreSQL ve stejném regionu jako VM.
2. Pro staging použít samostatnou zonální instanci s automatickými zálohami a PITR.
3. Připojit databázi přes privátní IP a Cloud SQL Auth Proxy nebo Connector.
4. Databázové heslo/connection údaje držet v Secret Manageru.
5. Aplikační service account omezit na nezbytné role.
6. Spustit migrace jako samostatný release krok před restartem aplikace.
7. Zapnout databázové alerty: CPU, paměť, disk, počet spojení, chyby a replikační stav.

Akceptace:

- VM nemá databázové heslo zapsané v image ani repozitáři.
- Databáze není veřejně přístupná.
- Obnova ze zálohy a PITR je nacvičena do nové staging instance.
- Restart aplikace i VM zachová všechny aktivní relace.

## Fáze 4 – import stávajících JSON dat

Odhad: 1–2 dny.

1. Vytvořit read-only importní nástroj pro `sessions.json`, `lobbies.json`, `leaderboard.json` a `runtime_settings.json`.
2. Před importem ověřit JSON schéma a vazby session–lobby–hráči.
3. Import provádět idempotentně; opakované spuštění nesmí vytvořit duplicity.
4. Vygenerovat report:
   - počet relací,
   - počet lobby a hráčů,
   - počet výsledků,
   - relace bez lobby,
   - duplicity názvů a join kódů,
   - neznámé verze snapshotu.
5. Porovnat skóre, checkpointy a časové údaje před a po importu.
6. Exportovat databázi zpět do diagnostického JSON a porovnat významová data.

Akceptace: nulové nevysvětlené rozdíly a kompletní auditní report importu.

## Fáze 5 – zátěžové a provozní testy

Odhad: 2–3 dny.

1. Simulovat plánovaný maximální počet týmů a zařízení plus 50% rezervu.
2. Ověřit dlouhé WebSockety, reconnect, uspání telefonu a výměnu sítě.
3. Ověřit souběžné starty týmů a provozní limity.
4. Během hry restartovat aplikační kontejner a následně celou VM.
5. Simulovat krátký výpadek Cloud SQL a vyčerpání connection poolu.
6. Ověřit administrativní globální stop, vyhodnocení a export statistik.
7. Změřit latenci p95/p99, RAM, CPU, počet DB spojení a dobu obnovy relace.

Výchozí cíle:

- p95 běžné zprávy pod 300 ms v evropské síti,
- žádné smíchání dat mezi týmy,
- žádné dvojí bodování při opakované zprávě,
- obnova klienta po restartu aplikace do 15 sekund,
- úspěšný kompletní smoke test po každém deployi.

## Fáze 6 – produkční přepnutí

Odhad: 0,5–1 den plus dohled.

1. Minimálně 48 hodin předem snížit DNS TTL.
2. Označit ověřený Docker image neměnným release tagem.
3. Vyhlásit servisní okno a zastavit nové starty v admin dashboardu.
4. Počkat na dokončení nebo administrativně uzavřít rozehrané týmy.
5. Vytvořit finální JSON export, snapshot disku a databázovou zálohu.
6. Spustit finální import do produkční Cloud SQL.
7. Nasadit aplikaci s `PostgresStorage`, spustit migrace a smoke test.
8. Přepnout DNS až po ověření healthchecku, adminu, sóla a týmového lobby.
9. Po dobu prvního provozního dne sledovat logy, reconnecty, DB pool a chyby klientů.

Rollback podmínky:

- neúspěšný smoke test,
- chyba databázové migrace,
- ztráta nebo dvojí zápis skóre,
- nefunkční reconnect,
- p95 latence nad dohodnutým limitem.

Rollback postup:

1. Zastavit nové starty.
2. Vrátit DNS na původní endpoint nebo nasadit předchozí image.
3. Přepnout úložiště na JSON pouze tehdy, pokud po finálním exportu nevznikly nové produkční zápisy; jinak nejprve provést řízený export z PostgreSQL.
4. Uchovat chybovou databázi a logy pro analýzu, nepřepisovat je obnovou.

## Fáze 7 – stabilizace po spuštění

Odhad: první 1–2 týdny provozu.

1. Denně kontrolovat zálohy a alerty, týdně provést test obnovitelnosti exportu.
2. Nastavit retenční a mazací úlohy podle schválených pravidel.
3. Přidat dashboard pro aktivní týmy, WebSockety, chyby, DB latenci a reconnecty.
4. Sepsat runbook pro výpadek VM, Cloud SQL, DNS, certifikátu a chybné nasazení.
5. Po stabilizaci rozhodnout, zda samostatná Cloud SQL stačí, nebo je nutné regionální HA.

## Fáze 8 – průběžný deploy změn a oprav

Odhad zavedení: 2–4 dny. Poté jde o standardní proces každého releasu.

První implementace této fáze je připravena v `infra/terraform/` a `deploy/gcp/`: infrastruktura, Artifact Registry, bootstrap VM, samostatná dopředná migrace schématu, deploy podle digestu, readiness kontrola a aplikační rollback.

### Release infrastruktura

1. Ukládat produkční image do Artifact Registry, nikdy je nestavět přímo na produkční VM.
2. Použít Cloud Build nebo GitHub Actions s Workload Identity Federation; nepoužívat dlouhodobý JSON service-account klíč.
3. Každý image označit:
   - neměnným Git SHA,
   - čitelnou verzí `vX.Y.Z`,
   - prostředím pouze jako pohyblivým aliasem, nikoli jako jedinou identitou.
4. Staging a produkce používají stejný image digest. Produkce nesmí sestavovat jiný artefakt ze stejného commitu.
5. Uchovávat minimálně posledních pět ověřených produkčních image pro rychlý rollback.
6. Terraformem nebo jiným Infrastructure as Code spravovat VM, firewall, service accounts, Secret Manager, Cloud SQL, Artifact Registry, monitoring a snapshot policy.

### CI pipeline pro každý pull request

Povinné kontroly před sloučením:

1. Python unit a integrační testy.
2. Kompletní scenario journey smoke test.
3. Validace JSON scénáře a runtime konfigurace.
4. Kontrola syntaxe klientského JavaScriptu.
5. Statická analýza Pythonu a kontrola závislostí.
6. Sestavení Docker image.
7. Start image v dočasném kontejneru a ověření `/api/health` a `/api/ready`.
8. Test databázových migrací na prázdné PostgreSQL i kopii předchozího schématu.
9. Kontrola, že v repozitáři ani image nejsou tajemství, `.env`, certifikáty nebo produkční exporty.

Pull request nelze sloučit, pokud některá povinná kontrola neprojde.

### Automatický deploy na staging

Po sloučení do hlavní větve:

1. Sestavit image a publikovat ho do Artifact Registry pod Git SHA.
2. Vytvořit release manifest obsahující image digest, Git SHA, databázovou revizi a čas sestavení.
3. Spustit dopředné databázové migrace na stagingu.
4. Nasadit přesný image digest na staging VM.
5. Spustit healthcheck, WebSocket reconnect test a automatický průchod scénářem.
6. Při chybě automaticky vrátit předchozí image; databázi vracet pouze podle explicitního migračního postupu.
7. Označit image jako kandidáta pro produkci pouze po úspěšném smoke testu.

### Produkční deploy běžné změny

Produkce se spouští ručně z již ověřeného release kandidáta:

1. Zkontrolovat stav monitoringu, poslední zálohu a volné místo.
2. V admin dashboardu zastavit nové starty týmů.
3. Pokud změna není plně kompatibilní s běžícími relacemi, počkat na dokončení týmů nebo vyhlásit servisní okno.
4. Vytvořit on-demand databázovou zálohu/export a zaznamenat aktuální image digest.
5. Spustit pouze předem ověřené, zpětně kompatibilní migrace.
6. Stáhnout nový image podle digestu, nikoli podle samotného tagu `latest`.
7. Spustit nový kontejner, ověřit readiness a teprve potom přepnout Caddy.
8. Původní kontejner ponechat krátce dostupný pro okamžitý aplikační rollback, pokud to dovoluje databázová kompatibilita.
9. Spustit produkční smoke test: lobby, sólo start, týmové připojení, WebSocket, admin a health endpoint.
10. Znovu povolit start týmů a alespoň 30 minut sledovat zvýšený dohled.

### Kompatibilita rozehraných her

Každá změna herního snapshotu musí splnit jednu z možností:

- nový kód umí načíst aktuální i předchozí `schema_version`, nebo
- před deployem jsou všechny rozehrané relace dokončené či administrativně uzavřené.

Změna scénáře nesmí tiše změnit význam již uloženého checkpointu. Pokud se mění ID, odměna, závislost nebo pravidlo minihry, musí existovat explicitní migrace snapshotu a test obnovení staré relace.

### Databázové migrace bez odstávky

Používat vzor expand–migrate–contract:

1. **Expand:** přidat nové nullable sloupce/tabulky bez odstranění starých.
2. **Migrate:** nasadit kód, který zvládá starý i nový formát, a převést existující data.
3. **Contract:** staré sloupce odstranit až v pozdějším releasu po ověření a skončení rollback okna.

Ve stejném releasu se nemá současně odstranit databázové pole a nasadit kód, který jej už neumí číst. Destruktivní migrace vyžaduje samostatné schválení a ověřenou zálohu.

### Deploy urgentní opravy

Hotfix má zkrácený, ale nevynechaný proces:

1. Vytvořit větev z aktuálně nasazeného produkčního tagu, ne automaticky z hlavní větve.
2. Přidat regresní test reprodukující chybu.
3. Spustit povinné unit testy, scenario smoke test, build image a migrační kontrolu.
4. Nasadit hotfix nejprve na staging a provést cílený test opravené cesty.
5. Pokud chyba ohrožuje integritu dat, globálně zastavit provoz ještě před deployem.
6. Publikovat nový patch release, například `v1.4.2`, a nasadit ho standardním produkčním krokem.
7. Opravu následně sloučit zpět do hlavní vývojové větve.
8. Do 48 hodin doplnit krátký incident report: příčina, dopad, detekce, oprava a prevence.

### Rollback aplikace

Rollback smí používat pouze známý předchozí image digest:

1. Zastavit nové starty týmů.
2. Přepnout Caddy nebo Compose na předchozí image.
3. Ověřit health/readiness a reconnect jedné testovací relace.
4. Znovu povolit provoz až po smoke testu.

Pokud nový release provedl pouze kompatibilní expand migraci, databáze se při aplikačním rollbacku nevrací. Pokud databáze kompatibilní není, jde o databázový incident a obnova se provádí podle samostatného runbooku; automatické spuštění downgrade SQL není bezpečný výchozí postup.

### Evidence každého releasu

U každého produkčního nasazení uchovat:

- verzi a Git SHA,
- image digest,
- revizi databázového schématu,
- osobu, která deploy schválila,
- čas začátku a konce,
- odkaz na CI běh,
- výsledek smoke testu,
- vytvořenou zálohu,
- případný rollback nebo incident.

### Doporučené release rytmy

- běžné opravy a menší změny: plánované okno jednou týdně,
- změny scénáře nebo persistence: samostatné servisní okno,
- bezpečnostní hotfix: podle závažnosti okamžitě,
- aktualizace operačního systému: měsíční okno po ověření na staging VM,
- major upgrade PostgreSQL: samostatný projekt s nácvikem obnovy.

## Navazující vysoká dostupnost

Teprve po stabilní databázové migraci:

1. Přidat Memorystore for Redis pro pub/sub, přítomnost a distribuované zámky.
2. Převést procesní broadcasty na sdílenou vrstvu.
3. Ověřit idempotenci všech bodovaných operací.
4. Nasadit dvě aplikační instance za load balancer.
5. Případně přejít na Cloud Run nebo Managed Instance Group.
6. Cloud SQL změnit na regionální HA, pokud požadované RTO ospravedlní přibližně dvojnásobnou cenu databáze.

## Doporučené pořadí realizace

```text
Compute Engine staging
        ↓
abstrakce Storage + testy
        ↓
PostgresStorage + migrace
        ↓
Cloud SQL staging
        ↓
JSON import a validační report
        ↓
zátěžové a recovery testy
        ↓
produkční přepnutí
        ↓
CI/CD pro změny a hotfixy
        ↓
Redis a více instancí pouze podle potřeby
```

## Odhad celku

Pro jednoho vývojáře přibližně 12–20 pracovních dní včetně stagingu, importu, testů obnovy, produkčního přepnutí a základní CI/CD pipeline. Samotné vytvoření VM je malá část práce; největší riziko a objem představuje bezpečný přesun persistence, souběžné zápisy, kompatibilní databázové migrace a ověřený rollback.

## Oficiální dokumentace

- [Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres)
- [Cloud SQL zálohy](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud SQL vysoká dostupnost](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [Compute Engine snapshoty](https://docs.cloud.google.com/compute/docs/disks/snapshots)
- [Doporučení pro konzistentní snapshoty](https://docs.cloud.google.com/compute/docs/disks/snapshot-best-practices)
