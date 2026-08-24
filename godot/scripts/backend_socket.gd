class_name EscapeBackendSocket
extends Node

signal connection_changed(connected)
signal message_received(message)
signal status_changed(text)

var socket := WebSocketClient.new()
var endpoint := "wss://localhost:8088/ws"
var connected := false
var request_counter := 0

func _ready() -> void:
	socket.connect("connection_established", self, "_on_connection_established")
	socket.connect("connection_closed", self, "_on_connection_closed")
	socket.connect("connection_error", self, "_on_connection_error")
	socket.connect("data_received", self, "_on_data_received")

func connect_backend(url: String = endpoint, allow_self_signed := true) -> void:
	endpoint = url
	socket.verify_ssl = not allow_self_signed
	var error := socket.connect_to_url(endpoint)
	if error != OK:
		emit_signal("status_changed", "Spojeni se nepodarilo zahajit: kod %s" % error)
	else:
		emit_signal("status_changed", "Pripojuji %s" % endpoint)

func _process(_delta: float) -> void:
	if socket.get_connection_status() != NetworkedMultiplayerPeer.CONNECTION_DISCONNECTED:
		socket.poll()

func _on_connection_established(_protocol := "") -> void:
	connected = true
	emit_signal("connection_changed", true)
	emit_signal("status_changed", "Backend pripojen")
	send_message("client.hello", {"client_name": "CHRONOS 3D", "protocol_version": 1})

func _on_connection_closed(_clean := false) -> void:
	connected = false
	emit_signal("connection_changed", false)
	emit_signal("status_changed", "Backend odpojen")

func _on_connection_error() -> void:
	connected = false
	emit_signal("connection_changed", false)
	emit_signal("status_changed", "Chyba spojeni s backendem")

func _on_data_received() -> void:
	var packet := socket.get_peer(1).get_packet().get_string_from_utf8()
	var parsed := JSON.parse(packet)
	if parsed.error == OK and parsed.result is Dictionary:
		emit_signal("message_received", parsed.result)

func send_message(type: String, payload: Dictionary = {}) -> bool:
	if not connected:
		emit_signal("status_changed", "Akce zustala lokalni - backend neni pripojen")
		return false
	request_counter += 1
	var message := {
		"type": type,
		"request_id": "chronos-3d-%d" % request_counter,
		"payload": payload,
	}
	return socket.get_peer(1).put_packet(JSON.print(message).to_utf8()) == OK
