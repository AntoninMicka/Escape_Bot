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
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be staging or production."
  }
}

variable "domain" {
  description = "Public DNS name which will point to the reserved VM IP."
  type        = string
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
