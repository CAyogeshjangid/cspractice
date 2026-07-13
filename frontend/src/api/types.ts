export interface Company {
  id: string;
  cin: string;
  name: string;
  registration_number: string | null;
  incorporation_date: string | null;
  category: string | null;
  status: string | null;
  registered_address: string | null;
  email: string | null;
  phone: string | null;
  fy_end_month: number;
  fy_end_day: number;
  agm_date: string | null;
  is_listed: boolean;
  paidup_capital: number | null;
  professional_group_id: string | null;
  industry_id: string | null;
}

export interface Taxonomy {
  id: string;
  name: string;
}

export interface Disclosure {
  director_id: string;
  fy: number;
  mbp1_received: string | null;
  dir8_received: string | null;
  dir2_received: string | null;
}

export interface Director {
  id: string;
  name: string;
  din: string | null;
  din_status: string | null;
  din_allocation_date: string | null;
  designation: string | null;
  appointment_date: string | null;
  cessation_date: string | null;
  is_active: boolean;
}

export interface Shareholder {
  id: string;
  name: string;
  folio: string | null;
  shares: string | null;
  percentage: string | null;
  category: string | null;
}

export interface CalendarRow {
  id: string;
  fy: number;
  category: string;
  obligation_name: string;
  form_number: string | null;
  rule_code: string;
  rule_version: number;
  citation: string;
  occurrence_label: string;
  subject_type: string;
  computed_due_date: string | null;
  override_date: string | null;
  override_reason: string | null;
  extension_date: string | null;
  extension_ref: string | null;
  effective_due_date: string | null;
  status: "pending" | "in_progress" | "filed" | "not_applicable";
  srn: string | null;
  filed_offline_ack: boolean;
  assignee_user_id: string | null;
  remarks: string | null;
  needs_review: boolean;
  needs_review_reason: string | null;
}

export interface TeamMember {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface DocTemplate {
  code: string;
  name: string;
  governing_reference: string;
  version: number;
  is_active: boolean;
  validated: boolean;
  validated_by: string | null;
  validated_at: string | null;
}

export interface GeneratedDoc {
  id: string;
  template_code: string;
  template_name: string;
  template_version: number;
  letterhead: string;
  generated_at: string;
  download: string;
}

export interface DeadLetter {
  id: string;
  scheduled_for: string;
  status: string;
  attempt_count: number;
  error: string | null;
  subject_kind: string;
  subject_label: string | null;
}

export interface DscReminderPolicy {
  days_before: number[];
  recipients: string[];
}

export interface ImportReport {
  rows_ok: number;
  errors: { row: number; column: string; error: string }[];
  imported?: boolean;
  dry_run?: boolean;
  created?: number;
  updated?: number;
  restored?: number;
  unchanged?: number;
  skipped?: number;
}
