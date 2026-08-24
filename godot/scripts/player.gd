class_name ChronosPlayer
extends KinematicBody

signal interaction_requested

export var speed := 6.0
export var mouse_sensitivity := 0.0022

var camera: Camera
var velocity := Vector3.ZERO

func _ready() -> void:
	camera = Camera.new()
	camera.position.y = 1.62
	add_child(camera)

	var collider := CollisionShape.new()
	var capsule := CapsuleShape.new()
	capsule.radius = 0.36
	capsule.height = 1.8
	collider.shape = capsule
	collider.position.y = 0.9
	add_child(collider)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		camera.rotation.x = clamp(camera.rotation.x - event.relative.y * mouse_sensitivity, -1.45, 1.45)
	elif event.is_action_pressed("release_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event.is_action_pressed("interact"):
		emit_signal("interaction_requested")

func _physics_process(delta: float) -> void:
	var input_vector := Vector2(
		Input.get_action_strength("move_right") - Input.get_action_strength("move_left"),
		Input.get_action_strength("move_back") - Input.get_action_strength("move_forward")
	).limit_length(1.0)
	var direction := (transform.basis * Vector3(input_vector.x, 0.0, input_vector.y)).normalized()
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	if not is_on_floor():
		velocity.y -= 18.0 * delta
	else:
		velocity.y = -0.1
	velocity = move_and_slide(velocity, Vector3.UP)
