# Automaticky vytvořeno Escape Bot Cloud Operatorem; neobsahuje tajemství.
project_id = "ztracena"
region = "europe-west3"
zone = "europe-west3-a"
environment = "event-2026"
domain = ""
machine_type = "e2-medium"
boot_disk_size_gb = 20
data_disk_size_gb = 10
enable_cloud_sql = false
data_snapshot_retention_days = 7
keep_snapshots_after_disk_delete = false
initial_image = "us-docker.pkg.dev/cloudrun/container/hello:latest"
labels = { lifecycle = "short-run", event = "event-2026" }
