/** Where a pesticide label rule came from. "fictional_sample" rules are seeded test data, never guidance. */
export type Provenance = "fictional_sample" | "reference" | "submitted";

export type Role = "farmer" | "provider" | "buyer" | "reviewer" | "admin";

export type Me = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  organization_id: number | null;
  organization_name: string | null;
  phone: string | null;
  notify_email: boolean;
  preferred_language: "en" | "ml" | "ta" | "pa" | "hi";
};

export type Page<T> = { items: T[]; total: number; page: number; page_size: number; unread_count?: number };

export type Crop = { id: number; code: string; name: string; scientific_name: string | null; category: string; growth_stages: string[]; pollinator_dependent: boolean; vision_supported: boolean };

export type CycleBrief = {
  id: number;
  crop: { id: number; name: string; code: string };
  variety: string | null;
  season: string | null;
  status: string;
  current_stage: string | null;
  sowing_date: string;
  expected_flowering_start: string | null;
  expected_flowering_end: string | null;
  expected_harvest_date: string | null;
  field: { id: number; name: string; area_ha: number };
  farm: { id: number; name: string; district: string; timezone?: string };
};

export type CycleDetail = CycleBrief & {
  growth_stages: string[];
  vision_supported: boolean;
  pollinator_dependent: boolean;
  stage_records: { id: number; stage: string; observed_on: string; notes: string | null }[];
};

export type FieldT = { id: number; farm_id: number; name: string; area_ha: number; soil_type: string | null; irrigation: string | null; cycles: CycleBrief[] };
export type Farm = {
  id: number; name: string; village: string | null; district: string; state: string; timezone: string;
  latitude: number | null; longitude: number | null; field_count: number; total_area_ha: number; active_cycle_count: number; fields?: FieldT[];
};

export type Prediction = {
  id: number; status: string; status_reason: string | null; model_key: string; model_version: string | null;
  predicted_class: string | null; predicted_crop: string | null; predicted_condition: string | null; confidence: number | null;
  top_k: { class: string; crop: string; condition: string; probability: number }[]; processing_ms: number | null;
  review_recommended: boolean; created_at: string;
};
export type Review = { id: number; decision: string; reviewed_label: string | null; notes: string | null; recommended_action: string | null; reviewer: string; prediction_id: number | null; created_at: string };
export type CycleCtx = { id: number; crop: string; crop_code: string; vision_supported: boolean; field: string; farm: string; district: string };
export type Observation = {
  id: number; crop_cycle_id: number; observed_at: string; notes: string | null; status: string; review_status: string; has_image: boolean;
  prediction: Prediction | null; latest_review: Review | null; cycle: CycleCtx;
  predictions?: Prediction[]; reviews?: Review[]; image?: { width: number; height: number; size_bytes: number; source_note: string | null } | null;
  can_review?: boolean; can_reanalyze?: boolean;
};

export type Outcome = {
  application_id: number; product_name: string; application_date: string; resolved: boolean; phi_days: number | null;
  earliest_eligible_date: string | null; label_id: number | null; label_version: string | null; source_reference: string | null;
  issue: string | null; issue_message: string | null; warnings: string[]; provenance: Provenance | null;
};
export type Assessment = {
  status: "restricted" | "upcoming" | "eligible" | "unknown"; as_of_date: string; timezone: string; earliest_eligible_date: string | null;
  days_until_eligible: number | null; governing_application_id: number | null; unresolved_count: number; rule_version: string; uses_fictional_reference: boolean; outcomes: Outcome[];
};
export type Application = {
  id: number; crop_cycle_id: number; product: { id: number; trade_name: string; active_ingredient: string | null }; applied_at: string;
  dose_value: number; dose_unit: string; treated_area_ha: number | null; application_method: string | null; target_problem: string | null;
  recorded_phi_days: number | null; notes: string | null; status: string; void_reason: string | null; voided_at: string | null; recorded_by: string | null; created_at: string;
};
export type Label = {
  id: number; product_id: number; product_name: string | null; crop: { id: number; name: string }; label_version: string; phi_days: number | null;
  dose_min: number | null; dose_max: number | null; dose_unit: string | null; source_reference: string; source_kind: string; provenance: Provenance; verification_status: string;
  verified_at: string | null; valid_from: string; valid_until: string | null; notes: string | null; created_at: string;
};
export type Product = { id: number; trade_name: string; active_ingredient: string | null; formulation: string | null; product_type: string | null; registrant: string | null; registration_ref: string | null; labels: Label[] };

export type Provider = {
  id: number; display_name: string; provider_type: string; pollinator: string; base_district: string; base_state: string;
  service_radius_km: number | null; colonies_total: number; is_active: boolean; crops: { id: number; name: string }[];
  service_areas: { id: number; district: string; state: string }[]; has_location: boolean; description?: string | null; contact_phone?: string | null;
  availability?: { id: number; start_date: string; end_date: string; colonies_available: number; min_free: number; notes: string | null }[];
};
export type Booking = {
  id: number; status: string; start_date: string; end_date: string; colonies_requested: number; proposed_start_date: string | null; proposed_end_date: string | null;
  farmer_note: string | null; provider_note: string | null; version: number; created_at: string; updated_at: string;
  provider: { id: number; display_name: string; contact_phone: string | null };
  cycle: { id: number; crop: string; field: string; area_ha: number; farm: string; district: string; state: string; village: string | null; flowering_start: string | null; flowering_end: string | null };
  events?: { from: string | null; to: string; note: string | null; actor: string | null; at: string }[];
};
export type ProviderMatch = { provider: Provider; eligible: boolean; score: number | null; distance_km: number | null; free_colonies: number; covered_days: number; window_days: number; reasons: string[]; exclusions: string[] };

export type Shipment = { id: number; status: string; scheduled_date: string | null; events: { status: string; note: string | null; at: string }[] };
export type Assignment = {
  id: number; buyer: { id: number; display_name: string; district: string; buyer_type: string }; demand_id: number | null; quantity_kg: number;
  status: string; reason: string; assigned_at: string; ended_at: string | null; end_reason: string | null; shipment: Shipment | null;
};
export type Batch = {
  id: number; code: string; crop: { id: number; name: string }; crop_cycle_id: number | null; source: { field: string; farm: string; district: string } | null;
  quantity_value: number; unit: string; quantity_kg: number; grade: string; quality_notes: string | null; harvested_on: string; shelf_life_days: number | null;
  shelf_life_source: string | null; storage_condition: string | null; available_from: string; deliver_by: string | null; sell_by: string | null;
  days_left: number | null; urgency: "critical" | "high" | "normal" | "unknown"; status: string; harvest_check_status: string | null; version: number;
  harvest_check_details?: { unresolved_count?: number; uses_fictional_reference?: boolean } | null;
  current_assignment: Assignment | null; created_at: string; assignments?: Assignment[]; latest_run?: RerouteRun | null;
};
export type Match = {
  id: number; buyer: { id: number; display_name: string; buyer_type: string; district: string; state: string; delivery_preference: string };
  demand: { id: number; accepted_grades: string[]; quantity_kg: number; delivery_start: string; delivery_end: string; max_distance_km: number | null };
  eligible: boolean; score: number | null; rank: number | null; distance_km: number | null; remaining_demand_kg: number | null;
  components: Record<string, number>; reasons: string[]; tradeoffs: string[]; exclusions: string[];
};
export type RerouteRun = { id: number; trigger: string; note: string | null; as_of_date: string; scoring_version: string; created_at: string; matches: Match[] };
export type Demand = {
  id: number; crop: { id: number; name: string }; accepted_grades: string[]; quantity_kg: number; allocated_kg: number; remaining_kg: number;
  valid_from: string; valid_until: string; delivery_start: string; delivery_end: string; max_distance_km: number | null; status: string; notes: string | null;
};
export type Notification = { id: number; event_type: string; title: string; body: string | null; entity_type: string | null; entity_id: number | null; link: string | null; severity: string; read_at: string | null; created_at: string };
