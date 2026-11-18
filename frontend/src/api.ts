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
  order: number
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
}

export interface StaySuggestion {
  name: string
  address: string | null
  business_area: string | null
  stay_type: string | null
  distance_m: number | null
  avg_attraction_distance_m: number | null
  cost_amount: number | null
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

export function planMapUrl(planId: number, dayIndex: number): string {
  return `${API_BASE}/plans/${planId}/days/${dayIndex}/map`
}

export function mealSuggestions(
  planId: number,
  dayIndex: number,
  mealType: string,
): Promise<{ items: MealSuggestion[]; total: number }> {
  return request(
    `/plans/${planId}/days/${dayIndex}/meals/${mealType}/suggestions`,
  )
}

export function staySuggestions(
  planId: number,
): Promise<{ items: StaySuggestion[]; total: number }> {
  return request(`/plans/${planId}/stays/suggestions`)
}
