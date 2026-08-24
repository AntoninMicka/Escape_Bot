extends Spatial

const PRESENT := Color("#76818c")
const FUTURE := Color("#5ad7c8")
const WALL := Color("#c5c8c4")
const DARK := Color("#273039")
const GARDEN := Color("#557a5b")
const LAB := Color("#b7d5db")

var player: ChronosPlayer
var backend: EscapeBackendSocket
var layer_label: Label
var prompt_label: Label
var message_label: Label
var status_label: Label
var future_layer := false
var terminals := []
var layer_materials := []

func _ready() -> void:
	_configure_input()
	_build_environment()
	_build_institute()
	_build_player()
	_build_ui()
	_build_backend()

func _configure_input() -> void:
	var bindings := {
		"move_forward": KEY_W,
		"move_back": KEY_S,
		"move_left": KEY_A,
		"move_right": KEY_D,
		"interact": KEY_E,
		"toggle_layer": KEY_T,
		"release_mouse": KEY_ESCAPE,
	}
	for action in bindings:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
		var event := InputEventKey.new()
		event.scancode = bindings[action]
		InputMap.action_add_event(action, event)

func _process(_delta: float) -> void:
	var nearest := _nearest_terminal()
	prompt_label.text = "[E] %s" % nearest.label if not nearest.empty() else ""
	if Input.is_action_just_pressed("toggle_layer"):
		_toggle_time_layer()

func _build_environment() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#101820")
	environment.ambient_light_color = Color("#d9e4e8")
	environment.ambient_light_energy = 0.72
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	world.environment = environment
	add_child(world)

	var sun := DirectionalLight.new()
	sun.rotation_degrees = Vector3(-58, -28, 0)
	sun.light_energy = 1.05
	sun.shadow_enabled = true
	add_child(sun)

func _build_institute() -> void:
	# Podlaha a obvodovy kriz chodeb.
	_add_box("Zaklad", Vector3(0, -0.3, 0), Vector3(54, 0.6, 42), DARK, true)
	_add_room("ATRIUM", Vector3(0, 0, 12), Vector3(16, 5, 12), PRESENT)
	_add_room("UBIKACE", Vector3(-17, 0, 0), Vector3(14, 4, 16), Color("#9b876f"))
	_add_room("REKREACNI ZAHRADA", Vector3(17, 0, 0), Vector3(14, 4, 16), GARDEN, false)
	_add_room("HLAVNI LABORATOR", Vector3(0, 0, -14), Vector3(20, 6, 14), LAB)
	_add_box("Chodba", Vector3(0, 0.08, 0), Vector3(10, 0.16, 18), Color("#515e66"), true)

	# Charakteristicke dominanty jednotlivych zon.
	_add_box("Recepce", Vector3(0, 0.65, 10), Vector3(6, 1.3, 1.2), Color("#354651"), true)
	_add_terminal("Recepcni terminal", Vector3(0, 1.65, 9.35), "reception_archive")
	for index in range(3):
		_add_box("Luzko%d" % index, Vector3(-20 + index * 3.2, 0.55, 1.5), Vector3(2.2, 1.1, 4.2), Color("#52606d"), true)
	_add_terminal("Elarin osobni zaznam", Vector3(-17, 1.4, -3.3), "elara_quarters")

	for x in [-2.8, 2.8]:
		_add_box("Strom", Vector3(17 + x, 1.4, 0), Vector3(0.55, 2.8, 0.55), Color("#594b35"), true)
		_add_box("Koruna", Vector3(17 + x, 3.2, 0), Vector3(3.0, 2.0, 3.0), Color("#4e8a61"), false)
	_add_box("Odpocinkova lavice", Vector3(17, 0.55, 4), Vector3(5, 1.1, 1.2), Color("#886e4e"), true)
	_add_terminal("Zahradni casova kotva", Vector3(17, 1.1, -4.5), "garden_anchor")

	_add_box("Stroj casu", Vector3(0, 1.8, -15), Vector3(5, 3.6, 5), Color("#263b49"), true)
	for offset in [Vector3(-4, 1.0, -14), Vector3(4, 1.0, -14)]:
		_add_box("Laboratorni pult", offset, Vector3(2.8, 2, 6), Color("#617981"), true)
	_add_terminal("Konzole projektu CHRONOS", Vector3(0, 1.35, -11.9), "chronos_console")

func _add_room(label: String, center: Vector3, size: Vector3, floor_color: Color, roof := true) -> void:
	_add_box(label + " podlaha", center + Vector3(0, 0.05, 0), Vector3(size.x, 0.1, size.z), floor_color, true)
	var thickness := 0.35
	var side_segment := (size.z - 3.0) / 2.0
	for side in [-1.0, 1.0]:
		for z_side in [-1.0, 1.0]:
			_add_box(
				label + " bocni stena",
				center + Vector3(side * size.x / 2.0, size.y / 2.0, z_side * (size.z + 3.0) / 4.0),
				Vector3(thickness, size.y, side_segment), WALL, true
			)
	if label == "ATRIUM":
		var rear_segment := (size.x - 4.0) / 2.0
		for x_side in [-1.0, 1.0]:
			_add_box(label + " zadni stena", center + Vector3(x_side * (size.x + 4.0) / 4.0, size.y / 2.0, -size.z / 2.0), Vector3(rear_segment, size.y, thickness), WALL, true)
	else:
		_add_box(label + " zadni", center + Vector3(0, size.y / 2, -size.z / 2), Vector3(size.x, size.y, thickness), WALL, true)
	if roof:
		_add_box(label + " strop", center + Vector3(0, size.y, 0), Vector3(size.x, 0.15, size.z), Color("#89939a"), false)

func _add_box(label: String, position: Vector3, size: Vector3, color: Color, collision: bool) -> MeshInstance:
	var body := StaticBody.new()
	body.name = label
	body.position = position
	add_child(body)
	var mesh_instance := MeshInstance.new()
	var mesh := CubeMesh.new()
	mesh.size = size
	var material := SpatialMaterial.new()
	material.albedo_color = color
	material.roughness = 0.78
	mesh.material = material
	mesh_instance.mesh = mesh
	body.add_child(mesh_instance)
	if collision:
		var shape := CollisionShape.new()
		var box := BoxShape.new()
		box.extents = size / 2.0
		shape.shape = box
		body.add_child(shape)
	if color in [PRESENT, LAB, GARDEN]:
		layer_materials.append(material)
	return mesh_instance

func _add_terminal(label: String, position: Vector3, checkpoint: String) -> void:
	var terminal := _add_box(label, position, Vector3(1.1, 1.8, 0.45), Color("#163c46"), true)
	var material := terminal.mesh.material as SpatialMaterial
	material.emission_enabled = true
	material.emission = Color("#43d4c4")
	material.emission_energy = 2.2
	terminals.append({"label": label, "position": position, "checkpoint": checkpoint})

func _build_player() -> void:
	player = ChronosPlayer.new()
	player.position = Vector3(0, 0.2, 16)
	player.connect("interaction_requested", self, "_interact")
	add_child(player)

func _build_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var overlay := ColorRect.new()
	overlay.color = Color(0.02, 0.04, 0.05, 0.68)
	overlay.rect_position = Vector2(18, 18)
	overlay.rect_size = Vector2(390, 126)
	canvas.add_child(overlay)
	var info := VBoxContainer.new()
	info.rect_position = Vector2(32, 28)
	info.rect_size = Vector2(360, 110)
	canvas.add_child(info)
	var title := Label.new()
	title.text = "USTAV CHRONOS // PROTOTYP"
	info.add_child(title)
	layer_label = Label.new()
	layer_label.text = "CASOVA VRSTVA: PRITOMNOST  [T]"
	info.add_child(layer_label)
	status_label = Label.new()
	status_label.text = "Backend: nepripojen"
	info.add_child(status_label)
	var controls := Label.new()
	controls.text = "WASD pohyb  •  mys rozhled  •  Esc uvolnit mys"
	info.add_child(controls)

	prompt_label = Label.new()
	prompt_label.rect_position = Vector2(0, 620)
	prompt_label.rect_size = Vector2(1280, 40)
	prompt_label.align = Label.ALIGN_CENTER
	canvas.add_child(prompt_label)
	message_label = Label.new()
	message_label.rect_position = Vector2(240, 660)
	message_label.rect_size = Vector2(800, 44)
	message_label.align = Label.ALIGN_CENTER
	message_label.autowrap = true
	canvas.add_child(message_label)

func _build_backend() -> void:
	backend = EscapeBackendSocket.new()
	backend.connect("status_changed", self, "_on_backend_status")
	backend.connect("message_received", self, "_on_backend_message")
	add_child(backend)
	backend.connect_backend()

func _nearest_terminal() -> Dictionary:
	var nearest: Dictionary = {}
	var best_distance := 2.7
	for terminal in terminals:
		var distance := player.global_position.distance_to(terminal.position)
		if distance < best_distance:
			best_distance = distance
			nearest = terminal
	return nearest

func _interact() -> void:
	var terminal := _nearest_terminal()
	if terminal.empty():
		message_label.text = "V dosahu neni zadny aktivni terminal."
		return
	message_label.text = "%s: synchronizace kotvy..." % terminal.label
	backend.send_message("player.message", {"text": "Aktivuji 3D terminal %s (%s)." % [terminal.label, terminal.checkpoint]})

func _toggle_time_layer() -> void:
	future_layer = not future_layer
	layer_label.text = "CASOVA VRSTVA: %s  [T]" % ("BUDOUCNOST" if future_layer else "PRITOMNOST")
	for material in layer_materials:
		material.emission_enabled = future_layer
		material.emission = FUTURE
		material.emission_energy = 0.7
	message_label.text = "Casova kotva ukazuje %s vrstvu ustavu." % ("budouci" if future_layer else "soucasnou")

func _on_backend_message(message: Dictionary) -> void:
	var type := str(message.get("type", ""))
	var payload: Dictionary = message.get("payload", {})
	if type == "bot.message":
		message_label.text = str(payload.get("text", "Prichozi zprava"))
	elif type == "game.state":
		message_label.text = "Stav mise: %s" % payload.get("phase", "neznamy")
	elif type == "error":
		message_label.text = "Backend: %s" % payload.get("message", "chyba")

func _on_backend_status(text: String) -> void:
	status_label.text = "Backend: " + text
