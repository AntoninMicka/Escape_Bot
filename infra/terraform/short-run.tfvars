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
initial_image = "europe-west3-docker.pkg.dev/ztracena/escape-bot/app@sha256:621f7d01bdfb3e34067c9a4a27a609adb1d8fd6901317988ff8009d85abe477c"
labels = { lifecycle = "short-run", event = "event-2026" }
