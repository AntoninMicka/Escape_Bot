class_name ChronosGameState
extends Node

signal objective_changed(objective, index, total)
signal inventory_changed(items)
signal story_message(text)
signal game_completed

const SAVE_PATH := "user://chronos_progress.cfg"

const MISSIONS := [
	{
		"id": "reception_archive", "label": "Recepcni archiv", "zone": "ATRIUM",
		"token": "4ec67b900c4a491ba180c8a48d5309f2", "answer": ["2147"],
		"prompt": "Urci pokoj doktorky Elary a pozici jejiho zaznamu. Kod tvori tri cislice pokoje a jedna cislice pozice.",
		"success": "Archiv potvrzuje Elaru v pokoji 214, pozice 7. Servisni otisk otevira dalsi cast ustavu.",
		"reward": "SERVISNI OTISK"
	},
	{
		"id": "staircase_signal", "label": "Schodistovy chronosignal", "zone": "SCHODISTE",
		"token": "74c67eaf38ef4b72b22f5c971b7bb7bd", "answer": ["BOWLING"],
		"prompt": "Obrazovy zaznam pouziva praporovou abecedu. Jake navigacni slovo tvori sedm znaku?",
		"success": "Signal prelozen: BOWLING. Diagnosticke kridlo je pristupne.", "reward": "SEMAFOROVA TABULKA"
	},
	{
		"id": "courtyard_minefield", "label": "Nestabilni nadvori", "zone": "ZAHRADA",
		"token": "6b0f716a2a264cc783d182b93f99a531", "answer": ["STABILNI", "STABILNÍ"],
		"prompt": "Projdi bezpecnou trasu mezi chronalnimi poli. Pro tento prototyp potvrd vysledek slovem STABILNI.",
		"success": "Trasa nadvorim je stabilni. Elara muze pokracovat k diagnostice.", "reward": "STABILNI TRASA"
	},
	{
		"id": "bowling_diagnostics", "label": "Binarni diagnostika", "zone": "DIAGNOSTIKA",
		"token": "a9dc930b787a4be6a5344e524d56073b", "answer": ["MOTOR"],
		"prompt": "Preved sekvenci 1001101 1001111 1010100 1001111 1010010 ze sedmibitoveho ASCII.",
		"success": "Temporalni motor byl synchronizovan s konzoli.", "reward": "TEMPORALNI MOTOR"
	},
	{
		"id": "timeline_calibration", "label": "Kalibrace casove osy", "zone": "DIAGNOSTIKA",
		"token": "9c6fa028b7614a669c9c43def9df1ba8", "answer": ["531"],
		"prompt": "Kalibracni protokol pozaduje pet trojic, tri ctverice a jednu petici. Zadej cil jako tri cislice.",
		"success": "Kalibrace 5-3-1 drzi. V zahrade se objevila chronalni ozvena.", "reward": "KALIBRACE 5-3-1"
	},
	{
		"id": "terrace_echo", "label": "Chronalni ozvena zahrady", "zone": "ZAHRADA",
		"token": "8fd7cd0a5c844702bc384665e864d335", "answer": ["HRISTE", "HŘIŠTĚ"],
		"prompt": "Morseuv prenos .... .-. .. ... - . oznacuje cilovou lokaci.",
		"success": "Fazovy stabilizator je znovu synchronizovan.", "reward": "FAZOVY STABILIZATOR"
	},
	{
		"id": "courtyard_alignment", "label": "Zarovnani casovych uzlu", "zone": "ZAHRADA",
		"token": "cb2ee52d5ae74fa6b68f94f59db75d63", "answer": ["TRI", "3"],
		"prompt": "Kolik smeru musi tym spolecne pokryt pri zarovnani uzlu?",
		"success": "Vodorovna, svisla a diagonalni osa jsou zarovnane.", "reward": "ZAROVNANE UZLY"
	},
	{
		"id": "sports_archive", "label": "Servisni archiv", "zone": "UBIKACE",
		"token": "de724be50829411287a0536095cc9148", "answer": ["NAPAJENI", "NAPÁJENÍ"],
		"prompt": "Presun energeticke clanky na cilova pole. Pro prototyp potvrd obnoveny system slovem NAPAJENI.",
		"success": "Vsechny servisni sektory jsou online a vydaly obe casti sifrovaci tabulky.", "reward": "SIFROVACI TABULKA"
	},
	{
		"id": "sports_cipher", "label": "Sifrovaci kotva", "zone": "UBIKACE",
		"token": "fbc646e76f0247d69589de21ea645f95", "answer": ["HODINY"],
		"prompt": "Sest ne znamych znaku maleho polskeho krize oznacuje predmet, ktery ukazuje cas.",
		"success": "Nalezen krystal casove kotvy a pristupovy otisk Archivu budoucnosti.", "reward": "KRYSTAL CASOVE KOTVY"
	},
	{
		"id": "future_archive", "label": "Archiv budoucnosti", "zone": "ARCHIV",
		"token": "4dc33e89b217a3a439dbb96e31c59ea4", "answer": ["2037 2140 MOTOR STABILIZATOR KRYSTAL"],
		"prompt": "Obnov navratovy vektor. Zadej rok, cas a poradi modulu bez interpunkce.",
		"success": "Navratovy vektor obnoven: 2037, 21:40, MOTOR - STABILIZATOR - KRYSTAL.", "reward": "NAVRATOVY VEKTOR"
	},
	{
		"id": "time_machine_console", "label": "Finalni konzole CHRONOS", "zone": "HLAVNI LABORATOR",
		"token": "b9ae752e80e5d4d85965e805bbc4b62f", "answer": ["AKTIVOVAT"],
		"prompt": "Vsechny moduly jsou vlozeny a vektor nastaven. Zadej AKTIVOVAT pro spusteni navratoveho koridoru.",
		"success": "Koridor je stabilni. Elara se vratila do pritomnosti. Mise splnena.", "reward": "ELARA ZACHRANENA"
	}
]

var current_index := 0
var inventory := []
var started_at := 0

func _ready() -> void:
	load_progress()

func current_mission() -> Dictionary:
	if current_index >= MISSIONS.size():
		return {}
	return MISSIONS[current_index]

func is_current(checkpoint_id: String) -> bool:
	var mission := current_mission()
	return not mission.empty() and mission.id == checkpoint_id

func submit(checkpoint_id: String, answer: String) -> Dictionary:
	var mission := current_mission()
	if mission.empty():
		return {"correct": false, "message": "Mise uz byla dokoncena."}
	if mission.id != checkpoint_id:
		return {"correct": false, "message": "Tato kotva zatim neni v aktivni trase."}
	var normalized := _normalize(answer)
	var correct := false
	for accepted in mission.answer:
		if normalized == _normalize(accepted):
			correct = true
			break
	if not correct:
		return {"correct": false, "message": "Konzole odpoved odmitla. Zkontroluj zaznamy a zkus to znovu."}
	if mission.reward != "" and not mission.reward in inventory:
		inventory.append(mission.reward)
	current_index += 1
	save_progress()
	emit_signal("story_message", mission.success)
	emit_signal("inventory_changed", inventory)
	if current_index >= MISSIONS.size():
		emit_signal("game_completed")
	else:
		emit_signal("objective_changed", current_mission(), current_index, MISSIONS.size())
	return {"correct": true, "message": mission.success}

func reset_progress() -> void:
	current_index = 0
	inventory.clear()
	started_at = OS.get_unix_time()
	save_progress()
	emit_signal("inventory_changed", inventory)
	emit_signal("objective_changed", current_mission(), current_index, MISSIONS.size())

func save_progress() -> void:
	var config := ConfigFile.new()
	config.set_value("game", "current_index", current_index)
	config.set_value("game", "inventory", inventory)
	config.set_value("game", "started_at", started_at)
	config.save(SAVE_PATH)

func load_progress() -> void:
	var config := ConfigFile.new()
	if config.load(SAVE_PATH) == OK:
		current_index = int(config.get_value("game", "current_index", 0))
		inventory = config.get_value("game", "inventory", [])
		started_at = int(config.get_value("game", "started_at", OS.get_unix_time()))
	else:
		started_at = OS.get_unix_time()
	call_deferred("_announce_loaded_state")

func _announce_loaded_state() -> void:
	emit_signal("inventory_changed", inventory)
	if current_index >= MISSIONS.size():
		emit_signal("game_completed")
	else:
		emit_signal("objective_changed", current_mission(), current_index, MISSIONS.size())

func _normalize(value: String) -> String:
	var text := value.strip_edges().to_upper()
	for pair in [["Á", "A"], ["Č", "C"], ["Ď", "D"], ["É", "E"], ["Ě", "E"], ["Í", "I"], ["Ň", "N"], ["Ó", "O"], ["Ř", "R"], ["Š", "S"], ["Ť", "T"], ["Ú", "U"], ["Ů", "U"], ["Ý", "Y"], ["Ž", "Z"]]:
		text = text.replace(pair[0], pair[1])
	text = text.replace(":", " ").replace("-", " ")
	while "  " in text:
		text = text.replace("  ", " ")
	return text
