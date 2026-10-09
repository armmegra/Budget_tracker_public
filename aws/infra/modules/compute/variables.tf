variable "name_prefix" {
  type = string
}

variable "source_dir" {
  description = "Absolute path to src/ - the directory holding handler.py and budget/."
  type        = string
}

variable "table_name" {
  type = string
}

variable "table_arn" {
  type = string
}

variable "timeout" {
  description = "Seconds. 30 matches the hand-built function; OCR is the slow path."
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "MB. Lambda scales CPU with memory, so this is a speed dial as much as a size one."
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "Never Expire is the default when Lambda creates the group itself; 14 is plenty here."
  type        = number
  default     = 14
}
