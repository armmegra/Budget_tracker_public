variable "name_prefix" {
  description = "Prefix for every resource name, e.g. budget-tracker-dev."
  type        = string
}

variable "account_id" {
  description = "Account id, appended to bucket names because S3 names are globally unique."
  type        = string
}

variable "deletion_protection" {
  description = "Refuse to delete the table. Off for dev, on for prod."
  type        = bool
  default     = false
}

variable "point_in_time_recovery" {
  description = "Continuous backups. Off for dev - it bills per GB of table size."
  type        = bool
  default     = false
}
