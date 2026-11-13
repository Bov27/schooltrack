/** API shapes used by the dashboard (subset of the OpenAPI schema). */

export type Role = "SCHOOL_ADMIN" | "TEACHER" | "STUDENT" | "STAFF" | "GUARDIAN";

export interface Membership {
  institution_id: string;
  institution_name: string;
  roles: Role[];
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  memberships: Membership[];
}

export interface Institution {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  is_active: boolean;
}

export interface Campus {
  id: string;
  name: string;
  address: string | null;
  timezone: string | null;
  is_active: boolean;
}

export interface Geofence {
  id: string;
  campus_id: string;
  name: string;
  is_active: boolean;
  area_m2: number;
  area: { type: "Polygon"; coordinates: number[][][] };
}

export interface LocationVerdict {
  verdict: "VALIDATED" | "FLAGGED_FOR_REVIEW" | "REJECTED";
  geofence_result: "INSIDE" | "OUTSIDE" | "NOT_EVALUATED";
  reasons: string[];
  geofence_id: string | null;
  distance_m: number | null;
}

export interface Student {
  id: string;
  student_code: string;
  full_name: string;
  date_of_birth: string | null;
  user_id: string | null;
  is_active: boolean;
}

export interface StaffMember {
  id: string;
  employee_code: string;
  staff_type: "TEACHER" | "ADMINISTRATIVE" | "SUPPORT";
  user_id: string;
  is_active: boolean;
}

export type ValidationStatus = "PENDING" | "VALIDATED" | "REJECTED" | "FLAGGED_FOR_REVIEW";

export interface AttendanceEvent {
  id: string;
  event_type: "CHECK_IN" | "TEMPORARY_CHECK_OUT" | "RETURN" | "CHECK_OUT";
  source: "MOBILE_GPS" | "MANUAL" | "OFFLINE_SYNC";
  campus_id: string;
  student_id: string | null;
  staff_id: string | null;
  state_before: string;
  state_after: string;
  validation_status: ValidationStatus;
  validation_reasons: string[];
  geofence_result: string;
  distance_to_geofence_m: number | null;
  occurred_at: string;
  location: { latitude: number; longitude: number; accuracy_m: number | null } | null;
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: { loc: unknown[]; msg: string }[] };
}
