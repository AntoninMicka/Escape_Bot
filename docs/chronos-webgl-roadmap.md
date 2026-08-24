# CHRONOS WebGL — další kroky

Aktualizováno: 24. 8. 2026

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
