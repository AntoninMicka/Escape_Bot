# Ztracená online: Ústav CHRONOS

První 3D prototyp scénáře nad existujícím Escape Bot backendem. Obsahuje průchozí
atrium, ubikace, rekreační zahradu a hlavní laboratoř, čtyři interaktivní terminály
a vizuální přepnutí mezi současnou a budoucí časovou vrstvou.

## Spuštění

1. Použijte Godot 3.5 (projekt je cílený na větev 3.x).
2. Importujte soubor `godot/project.godot` do Project Manageru.
3. Volitelně spusťte backend z kořene repozitáře pomocí `./start_backend.sh --demo`.
4. Spusťte projekt klávesou F6/F5.

Klient se standardně připojuje k `wss://localhost:8088/ws` a pro lokální vývoj
povoluje self-signed certifikát. Bez backendu zůstává svět normálně průchozí a
terminály fungují v lokálním prezentačním režimu.

## Ovládání

- `WASD`: pohyb
- myš: rozhled
- `E`: aktivace blízkého terminálu
- `T`: přepnutí časové vrstvy
- `Esc`: uvolnění kurzoru

Geometrie je záměrně generovaná ve `scripts/main.gd`. Díky tomu lze v této rané
fázi rychle měnit dispozici; po ověření měřítka se jednotlivé zóny převedou na
samostatné scény a nahradí finálními modely.
