variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Region for Compute Engine, Artifact Registry and Cloud SQL."
  type        = string
  default     = "europe-west3"
}

variable "zone" {
  description = "Compute Engine zone in the selected region."
  type        = string
  default     = "europe-west3-a"
}

variable "environment" {
  description = "Environment suffix used in resource names."
  type        = string
  default     = "staging"

  validation {
    condition     = can(regex("^(staging|production|event-[a-z0-9-]{1,12})$", var.environment))
    error_message = "Environment must be staging, production or a short event-* identifier."
  }
}

variable "domain" {
  description = "Optional public DNS name. Empty uses the reserved IPv4 address through sslip.io for short-lived environments."
  type        = string
  default     = ""
}

variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "boot_disk_size_gb" {
  type    = number
  default = 20
}

variable "data_disk_size_gb" {
  type    = number
  default = 30
}

variable "enable_cloud_sql" {
  description = "Provision PostgreSQL and its password secret. Disable for a single-VM short-run using JSON files on the persistent data disk."
  type        = bool
  default     = true
}

variable "database_tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "database_disk_size_gb" {
  type    = number
  default = 20
}

variable "database_availability_type" {
  description = "ZONAL for staging; REGIONAL is recommended for production after testing."
  type        = string
  default     = "ZONAL"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.database_availability_type)
    error_message = "Database availability type must be ZONAL or REGIONAL."
  }
}

variable "database_deletion_protection" {
  type    = bool
  default = true
}

variable "database_activation_policy" {
  description = "ALWAYS normally; short-run environments may be paused out of band with gcloud."
  type        = string
  default     = "ALWAYS"

  validation {
    condition     = contains(["ALWAYS", "NEVER"], var.database_activation_policy)
    error_message = "Database activation policy must be ALWAYS or NEVER."
  }
}

variable "database_pitr_enabled" {
  type    = bool
  default = true
}

variable "database_backup_retention_count" {
  type    = number
  default = 14
}

variable "database_transaction_log_retention_days" {
  type    = number
  default = 7
}

variable "data_snapshot_retention_days" {
  type    = number
  default = 14
}

variable "keep_snapshots_after_disk_delete" {
  type    = bool
  default = true
}

variable "initial_image" {
  description = "Immutable app image tag or digest used before the first deploy."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello:latest"
}

variable "ssh_via_iap" {
  description = "Allow SSH only from Google IAP TCP forwarding range."
  type        = bool
  default     = true
}

variable "labels" {
  type    = map(string)
  default = {}
}
