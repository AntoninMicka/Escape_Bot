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
initial_image = "europe-west3-docker.pkg.dev/ztracena/escape-bot/app@sha256:c01593e4f7591194282a565465d1a799214231ee1f5d5e767dc79974bfb5155c"
labels = { lifecycle = "short-run", event = "event-2026" }
