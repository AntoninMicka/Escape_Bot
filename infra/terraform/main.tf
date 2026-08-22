locals {
  prefix = "escape-bot-${var.environment}"
  labels = merge({
    application = "escape-bot"
    environment = var.environment
    managed_by  = "terraform"
  }, var.labels)

  required_apis = toset(concat([
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
  ], var.enable_cloud_sql ? [
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ] : []))

  effective_domain = trimspace(var.domain) != "" ? var.domain : "${replace(google_compute_address.app.address, ".", "-")}.sslip.io"
}

resource "google_project_service" "required" {
  for_each           = local.required_apis
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "main" {
  name                    = "${local.prefix}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "app" {
  name                     = "${local.prefix}-subnet"
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.40.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_services" {
  count         = var.enable_cloud_sql ? 1 : 0
  name          = "${local.prefix}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_services" {
  count                   = var.enable_cloud_sql ? 1 : 0
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services[0].name]
  depends_on              = [google_project_service.required]
}

resource "google_compute_address" "app" {
  name   = "${local.prefix}-ipv4"
  region = var.region
}

resource "google_compute_firewall" "web" {
  name    = "${local.prefix}-allow-web"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  allow {
    protocol = "udp"
    ports    = ["443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = [local.prefix]
}

resource "google_compute_firewall" "iap_ssh" {
  count   = var.ssh_via_iap ? 1 : 0
  name    = "${local.prefix}-allow-iap-ssh"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = [local.prefix]
}

resource "google_service_account" "app" {
  account_id   = "${local.prefix}-vm"
  display_name = "Escape Bot ${var.environment} VM"
  depends_on   = [google_project_service.required]
}

resource "google_project_iam_member" "cloud_sql_client" {
  count   = var.enable_cloud_sql ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = "escape-bot"
  description   = "Immutable Escape Bot application images"
  format        = "DOCKER"
  labels        = local.labels
  depends_on    = [google_project_service.required]
}

resource "google_secret_manager_secret" "admin_token" {
  secret_id = "${local.prefix}-admin-token"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "database_password" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = "${local.prefix}-database-password"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "admin_token_accessor" {
  secret_id = google_secret_manager_secret.admin_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

resource "google_secret_manager_secret_iam_member" "database_password_accessor" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = google_secret_manager_secret.database_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

resource "google_sql_database_instance" "main" {
  count               = var.enable_cloud_sql ? 1 : 0
  name                = "${local.prefix}-postgres"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.database_deletion_protection

  settings {
    tier              = var.database_tier
    availability_type = var.database_availability_type
    activation_policy = var.database_activation_policy
    disk_type         = "PD_SSD"
    disk_size         = var.database_disk_size_gb
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.database_pitr_enabled
      start_time                     = "02:00"
      transaction_log_retention_days = var.database_transaction_log_retention_days

      backup_retention_settings {
        retained_backups = var.database_backup_retention_count
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.main.id
      enable_private_path_for_google_cloud_services = true
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "500"
    }

    user_labels = local.labels
  }

  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "app" {
  count    = var.enable_cloud_sql ? 1 : 0
  name     = "escape_bot"
  instance = google_sql_database_instance.main[0].name
}

resource "google_compute_disk" "data" {
  name   = "${local.prefix}-data"
  zone   = var.zone
  type   = "pd-balanced"
  size   = var.data_disk_size_gb
  labels = local.labels
}

resource "google_compute_resource_policy" "daily_data_snapshot" {
  name   = "${local.prefix}-daily-data-snapshot"
  region = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "03:00"
      }
    }

    retention_policy {
      max_retention_days    = var.data_snapshot_retention_days
      on_source_disk_delete = var.keep_snapshots_after_disk_delete ? "KEEP_AUTO_SNAPSHOTS" : "APPLY_RETENTION_POLICY"
    }

    snapshot_properties {
      labels            = local.labels
      storage_locations = [var.region]
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "data_snapshot" {
  name = google_compute_resource_policy.daily_data_snapshot.name
  disk = google_compute_disk.data.name
  zone = var.zone
}

resource "google_compute_instance" "app" {
  name         = "${local.prefix}-vm"
  zone         = var.zone
  machine_type = var.machine_type
  tags         = [local.prefix]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = var.boot_disk_size_gb
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "escape-bot-data"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.app.id

    access_config {
      nat_ip = google_compute_address.app.address
    }
  }

  service_account {
    email  = google_service_account.app.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/templates/startup.sh.tftpl", {
    domain                  = local.effective_domain
    environment             = var.environment
    initial_image           = var.initial_image
    region                  = var.region
    storage_backend         = var.enable_cloud_sql ? "postgres" : "json"
    cloud_sql_connection    = var.enable_cloud_sql ? google_sql_database_instance.main[0].connection_name : ""
    admin_secret_id         = google_secret_manager_secret.admin_token.secret_id
    database_secret_id      = var.enable_cloud_sql ? google_secret_manager_secret.database_password[0].secret_id : ""
    database_user           = "escape_bot"
    database_name           = var.enable_cloud_sql ? google_sql_database.app[0].name : ""
    cloud_sql_proxy_version = "2.25.2"
  })

  depends_on = [
    google_project_iam_member.artifact_reader,
    google_project_iam_member.cloud_sql_client,
    google_secret_manager_secret_iam_member.admin_token_accessor,
    google_secret_manager_secret_iam_member.database_password_accessor,
  ]
}
