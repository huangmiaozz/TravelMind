const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

export interface TripSummary {
  id: number
  destination_city_name: string
  destination_city_adcode: string | null
  title: string
  plan_count: number
}

export interface PlanItem {
  poi_id: number
  name: string
  start_time: string
  end_time: string
  estimated_cost: number
  score: number
  opening_known: boolean
  opening_status?: string
  order: number
  ticket_price?: number | null
  ticket_child_price?: number | null
  ticket_status?: string
  ticket_source?: string | null
  ticket_source_url?: string | null
  ticket_verified_at?: string | null
  latitude: number | null
  longitude: number | null
}

export interface TransitSegment {
  mode: string
  line_name: string | null
  line_type: string | null
  departure_stop: string | null
  arrival_stop: string | null
  via_stops: number | null
  distance_m: number | null
  duration_s: number | null
  bike_distance_m: number | null
  bike_duration_s: number | null
}

export interface RouteLeg {
  from_poi_id: number
  to_poi_id: number
  mode: string
  distance_m: number | null
  duration_s: number | null
  walking_distance_m: number | null
  status: string
  source: string | null
  is_estimate: boolean
  fallback_duration_s: number | null
  error: string | null
  cost_amount: number | null
  cost_basis: string | null
  reason: string | null
  segments: TransitSegment[]
  walk_duration_s: number | null
  bike_duration_s: number | null
  bike_cost_amount: number | null
}

export interface DayWeather {
  status: string
  condition: string | null
  temperature_min: number | null
  temperature_max: number | null
  precipitation: number | null
  risk_level: string | null
  source: string | null
}

export interface MealBlock {
  meal_type: string
  start_time: string
  end_time: string
  duration_minutes: number
}

export interface MealSuggestion {
  name: string
  address: string | null
  distance_m: number | null
  cost_amount: number | null
  rating: number | null
  travel_minutes: number | null
  area_id: string | null
  area_name: string | null
  quality_tag: string | null
}

export interface MealArea {
  id: string
  name: string
  popularity: number
  travel_minutes: number
  note: string | null
  area_type: string
  weather_friendly: boolean
}

export interface StaySuggestion {
  name: string
  address: string | null
  business_area: string | null
  stay_type: string | null
  distance_m: number | null
  avg_attraction_distance_m: number | null
  avg_commute_minutes: number | null
  max_commute_minutes: number | null
  day_commutes: number[]
  tier: string | null
  cost_amount: number | null
  over_budget: boolean
  price_status: string | null
  price_source: string | null
  price_checked_at: string | null
  price_note: string | null
  rating: number | null
}

export interface DayPlan {
  travel_date: string
  items: PlanItem[]
  estimated_cost: number
  legs: RouteLeg[]
  weather: DayWeather | null
  walk_km: number | null
  walk_constraint: string
  meals: MealBlock[]
}

export interface CostBreakdown {
  tickets_amount: number
  tickets_status: string
  tickets_confirmed_amount: number
  tickets_estimated_amount: number
  tickets_unknown_count: number
  transport_amount: number
  transport_status: string
  meals_amount: number
  meals_status: string
  lodging_amount: number
  lodging_status: string
  total_estimated: number
  budget_total: number
  budget_difference: number
  budget_complete: boolean
  unknown_items: string[]
  updated_at?: string | null
}

export interface MealSelection {
  day_index: number
  meal_type: string
  name: string
  address: string | null
  area_id: string | null
  travel_minutes: number | null
  cost_amount: number | null
}

export interface StaySelection {
  name: string
  address: string | null
  business_area: string | null
  tier: string | null
  cost_amount: number | null
  price_status: string | null
  price_source: string | null
  price_checked_at: string | null
  price_note: string | null
  rating: number | null
}

export interface PlanSelections {
  meals: MealSelection[]
  stay: StaySelection | null
}

export interface PlanVersionSummary {
  plan_id: number
  version_no: number
  status: string
  start_date: string
  days: number
  adults: number
  children: number
  budget_total: number
  total_estimated_cost: number
  budget_difference: number
  over_budget: boolean
  weather_known: boolean
  generated_at: string
}

export interface PlanDetail {
  plan_id: number
  trip_id: number
  version_no: number
  days_count: number
  status: string
  city: string
  start_date: string
  generated_at: string
  days: DayPlan[]
  total_estimated_cost: number
  budget_total: number
  budget_difference: number
  over_budget: boolean
  weather_known: boolean
  notes: string[]
  source: string
  data_snapshot: Record<string, unknown>
  costs: CostBreakdown | null
}

export interface PlanRequest {
  city: string
  start_date: string
  days: number
  adults: number
  children: number
  budget_total: number
  interests: Record<string, number>
  pace: number
  transport_preference: string
  daily_start: string
  daily_end: string
  max_daily_items: number
  avoid_tight_schedule: boolean
  max_walk_km: number
  meal_budget_per_person_day?: number
  hotel_budget_per_room_night?: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : detail
    } catch {
      // 保留默认错误信息
    }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function createTrip(city: string, title: string): Promise<TripSummary> {
  return request('/trips', {
    method: 'POST',
    body: JSON.stringify({ city, title }),
  })
}

export function createPlan(tripId: number, payload: PlanRequest): Promise<PlanDetail> {
  return request(`/trips/${tripId}/plans`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listPlanVersions(
  tripId: number,
): Promise<{ items: PlanVersionSummary[]; total: number }> {
  return request(`/trips/${tripId}/plans`)
}

export function getPlanVersion(planId: number): Promise<PlanDetail> {
  return request(`/plans/${planId}`)
}

export function deletePlanVersion(planId: number): Promise<void> {
  return request(`/plans/${planId}`, { method: 'DELETE' })
}

export function getPlanSelections(planId: number): Promise<PlanSelections> {
  return request(`/plans/${planId}/selections`)
}

export function recalculatePlanCosts(planId: number): Promise<PlanDetail> {
  return request(`/plans/${planId}/costs/recalculate`, { method: 'POST' })
}

export function savePlanSelections(
  planId: number,
  selections: PlanSelections,
): Promise<PlanSelections> {
  return request(`/plans/${planId}/selections`, {
    method: 'PUT',
    body: JSON.stringify(selections),
  })
}

export function planMapUrl(planId: number, dayIndex: number): string {
  return `${API_BASE}/plans/${planId}/days/${dayIndex}/map`
}

export function mealAreas(
  planId: number,
  dayIndex: number,
  mealType: string,
): Promise<{
  items: MealArea[]
  meal_budget_minutes: number
  travel_budget_minutes: number
  min_eat_minutes: number
  total: number
}> {
  return request(
    `/plans/${planId}/days/${dayIndex}/meals/${mealType}/areas`,
  )
}

export function mealAreaRestaurants(
  planId: number,
  dayIndex: number,
  mealType: string,
  areaId: string,
): Promise<{ items: MealSuggestion[]; total: number }> {
  return request(
    `/plans/${planId}/days/${dayIndex}/meals/${mealType}/areas/${areaId}/restaurants`,
  )
}

export function searchMealAreaRestaurants(
  planId: number,
  dayIndex: number,
  mealType: string,
  areaId: string,
  query: string,
): Promise<{ items: MealSuggestion[]; total: number }> {
  return request(
    `/plans/${planId}/days/${dayIndex}/meals/${mealType}/areas/${areaId}/restaurants/search?q=${encodeURIComponent(query)}`,
  )
}

export function nearbyMeals(
  planId: number,
  dayIndex: number,
  mealType: string,
): Promise<{ items: MealSuggestion[]; total: number }> {
  return request(
    `/plans/${planId}/days/${dayIndex}/meals/${mealType}/nearby`,
  )
}

export function searchNearbyMeals(
  planId: number,
  dayIndex: number,
  mealType: string,
  query: string,
): Promise<{ items: MealSuggestion[]; total: number }> {
  return request(
    `/plans/${planId}/days/${dayIndex}/meals/${mealType}/nearby/search?q=${encodeURIComponent(query)}`,
  )
}

export function staySuggestions(
  planId: number,
): Promise<{ items: StaySuggestion[]; total: number }> {
  return request(`/plans/${planId}/stays/suggestions`)
}

export function searchStays(
  planId: number,
  query: string,
): Promise<{ items: StaySuggestion[]; total: number }> {
  return request(
    `/plans/${planId}/stays/search?q=${encodeURIComponent(query)}`,
  )
}
