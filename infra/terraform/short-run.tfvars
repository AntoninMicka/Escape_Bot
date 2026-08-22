# Automaticky vytvořeno Escape Bot Cloud Operatorem; neobsahuje tajemství.
project_id = "ztracena"
region = "europe-west3"
zone = "europe-west3-a"
environment = "event-2026"
domain = "136-92-9-129.sslip.io"
machine_type = "e2-medium"
boot_disk_size_gb = 20
data_disk_size_gb = 10
enable_cloud_sql = false
data_snapshot_retention_days = 7
keep_snapshots_after_disk_delete = false
initial_image = "europe-west3-docker.pkg.dev/ztracena/escape-bot/app@sha256:99d922fa73a3b25e60bbe53c41fda679d224279dea66b3602faea29243d77343"
labels = { lifecycle = "short-run", event = "event-2026" }
