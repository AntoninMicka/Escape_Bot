# CHRONOS WebGL — další kroky

Aktualizováno: 25. 8. 2026

## Nejbližší plán · doladění areálu po prvním hratelném průchodu

### 1. Dispozice a kolize

- [ ] Posunout sportovní hřiště tak, aby nekolidovalo s hlavní budovou ani přístupovými cestami.
- [ ] Vysunout schodiště nouzového východu mimo půdorys budovy.
- [ ] Ponechat otvor nouzového východu pouze ve stěně podzemního podlaží a v navazující podlaze exteriéru; ostatní stropy a podlahy uzavřít.
- [ ] Po změně znovu projít kolize budovy, hřiště, nouzového schodiště, podest a venkovní trasy oběma směry.

### 2. Ubytovací patra

- [ ] Přepracovat dispozici pokojů tak, aby měly uvěřitelné rozměry, chodbu, vstupy, dveře a smysluplné rozmístění vybavení.
- [ ] Odlišit jednotlivé pokoje a patra čísly, barvou nebo drobnými orientačními prvky.
- [ ] Ověřit, že postele, příčky a dveře neblokují chodbu, schodiště ani návrat z pokojů.

### 3. Rozšíření venkovního areálu

- [ ] Zvětšit terén kolem budovy a vytvořit přirozené odstupy mezi budovou, hřištěm, rybníkem a hranicí mapy.
- [ ] Oplotit hratelný areál a doplnit kolize plotu, aby hráč nemohl opustit určený prostor.
- [ ] Umístit horizontální kulisu s texturou až za plot a s dostatečným odstupem, aby nepůsobila jako dosažitelná stěna.
- [ ] Zakrýt hranici terénu vegetací, terénními zlomy nebo dalšími vrstvami kulisy a prověřit pohledy z terasy i vyšších pater.

### 4. Okna, materiály a textury

- [ ] Doplnit okna do fasády i pokojů s konzistentní výškou, rozestupy a bezpečným kolizním řešením.
- [ ] Navrhnout jednotnou sadu materiálů pro fasádu, interiéry, laboratoře, schodiště, komunikace, plot a venkovní povrchy.
- [ ] Otexturovat scénu a sjednotit měřítko UV; odstranit natažení, nápadné opakování a viditelné švy.
- [ ] Připravit samostatnou horizontální texturu odpovídající okolní krajině a otestovat ji za různého zorného pole.
- [ ] Po vizuálním průchodu změřit velikost assetů, dobu načtení, draw calls a snímkovou frekvenci ve Firefoxu i Chromiu.

Hotovo, když lze celý areál projít bez kolizních slepých míst, pokoje působí jako uvěřitelná součást budovy, hranice mapy je přirozeně skrytá a texturovaná scéna zůstane plynulá na cílových zařízeních.

## P0 — Spolehlivé zobrazení ve Firefoxu

- [ ] Reprodukovat problém na cílovém Firefoxu v Linuxu po čistém načtení a po aktualizaci service workeru.
- [ ] Prověřit WebGL kontext, velikost canvasu, framebuffer, resize, viditelnost stránky, cache a chybové výpisy v konzoli.
- [ ] Ověřit ovládání myší a klávesnicí, pointer lock a otevírání gadgetů po obnovení stránky.
- [ ] Přidat srozumitelnou diagnostiku a bezpečný fallback, pokud WebGL kontext nebo renderer selže.

Hotovo, když se po čistém startu i běžném reloadu zobrazí neprázdná scéna, nejsou přítomné fatální chyby a pohyb, interakce i gadgety fungují ve Firefoxu stejně jako v Chromiu.

## P1 — Ověření použitelnosti areálu

- [ ] Projít bez administrátorského zásahu celou trasu: recepce, pokoje a schodiště, bowling, terasa, venkovní hřiště, rybník a obě podzemní laboratorní úrovně.
- [ ] Ověřit čitelnost orientace, značení pater a místností, schodiště, dveře, kolize a návrat z vedlejších prostor.
- [ ] Otestovat interakční vzdálenosti, aby nešlo zařízení aktivovat přes stěnu nebo z jiného patra.
- [ ] Otestovat interkom, desky s hádankami, mapu, šifrovací pomůcky a detailní pohledy na zařízení bez ztráty stavu hry.
- [ ] Prověřit klávesnici a myš i mobilní dotykové ovládání, obnovení hry, respawn a ochranu proti uvíznutí.
- [ ] Zaznamenat místa, kde hráči bloudí, uvíznou nebo nerozpoznají další krok, a podle výsledků upravit dispozici či navigační vodítka.

Hotovo, když alespoň tři noví testující dokončí hlavní průchod bez technického zásahu, nenarazí na blokující kolizi nebo slepou past a dokážou používat všechny herní gadgety ve Firefoxu i Chromiu.

## P2 — Textury a výsledný vizuální průchod

- [ ] Vytvořit jednotný, původní vizuální styl výzkumného ústavu volně inspirovaného areálem Hotelu Kraskov.
- [ ] Odlišit materiály a atmosféru recepce, bowlingu, ubytovacích pater, terasy, laboratoří a venkovního areálu.
- [ ] Doplnit konzistentní měřítko UV, PBR materiály, značení, čísla pokojů, směrovky a environmentální vodítka.
- [ ] Ošetřit natažené textury, viditelné švy, opakování vzorů, průhlednost skel, vodní hladinu a pohled z terasy.
- [ ] Použít vlastní nebo licenčně doložené podklady a hlídat velikost textur, počet materiálů, draw calls, dobu načtení a snímkovou frekvenci.
- [ ] Po dokončení textur zopakovat celý test použitelnosti, kontrastu a čitelnosti interaktivních prvků.

Hotovo, když jsou jednotlivé zóny na první pohled rozlišitelné, navigace funguje i bez trvalého waypointu, nevyskytují se výrazné vizuální vady a cílová zařízení udrží plynulou scénu i přijatelnou dobu načtení.

## Doporučené pořadí

1. Stabilizovat Firefox, protože bez spolehlivého vykreslování nelze výsledky dalších testů hodnotit.
2. Ověřit průchodnost a orientaci ještě na současném grayboxu.
3. Až po ustálení dispozice dokončit textury, osvětlení a atmosféru.
4. Provedením závěrečného regresního playtestu uzavřít všechny tři body.
