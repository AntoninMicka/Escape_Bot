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
initial_image = "europe-west3-docker.pkg.dev/ztracena/escape-bot/app@sha256:4187512f7ca6bbdf8f58a342639786787c8457c3181b5ec7b4ed845e384fa406"
labels = { lifecycle = "short-run", event = "event-2026" }
