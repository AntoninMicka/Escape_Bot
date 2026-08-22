output "vm_name" {
  value = google_compute_instance.app.name
}

output "project_id" {
  value = var.project_id
}

output "vm_zone" {
  value = var.zone
}

output "public_ip" {
  value = google_compute_address.app.address
}

output "domain" {
  value = var.domain
}

output "cloud_sql_instance" {
  value = var.enable_cloud_sql ? google_sql_database_instance.main[0].name : null
}

output "cloud_sql_connection_name" {
  value = var.enable_cloud_sql ? google_sql_database_instance.main[0].connection_name : null
}

output "artifact_registry_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}

output "admin_token_secret" {
  value = google_secret_manager_secret.admin_token.secret_id
}

output "database_password_secret" {
  value = var.enable_cloud_sql ? google_secret_manager_secret.database_password[0].secret_id : null
}

output "service_account" {
  value = google_service_account.app.email
}
