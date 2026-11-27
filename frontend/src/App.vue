<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GlobeScene from './components/GlobeScene.vue'
import ChinaMapScene from './components/ChinaMapScene.vue'
import { createPlan, createTrip, deletePlanVersion, getPlanSelections, getPlanVersion, listPlanVersions, mealAreaRestaurants, mealAreas, nearbyMeals, planMapUrl, recalculatePlanCosts, savePlanSelections, searchMealAreaRestaurants, searchNearbyMeals, searchStays, staySuggestions, type MealArea, type MealSuggestion, type PlanDetail, type PlanSelections, type PlanVersionSummary, type StaySuggestion } from './api'

type DayPlan = PlanDetail['days'][number]
type PlanItem = DayPlan['items'][number]
type RouteLegItem = DayPlan['legs'][number]
type TransitStep = RouteLegItem['segments'][number]

type View = 'overview' | 'create' | 'plans' | 'stays'
type StoryPhase = 'earth' | 'focusing' | 'china-map' | 'planner'

// 三页叙事：0 地球 / 1 中国地图 / 2 规划页，每页正好一屏
const PAGE_COUNT = 3
// 滚轮冷却时间（毫秒），防止一次手势连跳多页
const WHEEL_COOLDOWN = 600
// 触发“地球转向中国”的阈值：滚动量超过约 0.35 屏即开始过渡
const TRANSITION_TRIGGER = 0.175
// 旋转定位完成后才开始放大：必须与 GlobeScene 的 ROTATE_END(0.65) 保持一致
const ZOOM_START = 0.65
// 放大幅度：实测过渡终态地球 transform 为 scale(3)，即原地球大小的 300%
const GLOBE_ZOOM_SCALE = 3

const activeView = ref<View>('overview')
const scrollProgress = ref(0)
// 地球组件产生的固定时长进度，驱动地图展开和地球淡出。
const focusProgress = ref(0)
// 地图在第三页要落到的位置：由左栏插槽实测得出，避免用 CSS 猜坐标
const mapShift = ref({ x: 0, y: 0, scale: 1 })
const storyRoot = ref<HTMLElement | null>(null)
const plannerScene = ref<HTMLElement | null>(null)
const mapSlot = ref<HTMLElement | null>(null)
let wheelLockedUntil = 0
const origin = ref('')
const destination = ref('')
const startDate = ref('')
const travelers = ref(2)
const days = ref(3)
const transportPreference = ref('auto')
const budget = ref('')
const showBrief = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const plan = ref<PlanDetail | null>(null)
const tripId = ref<number | null>(null)
const versions = ref<PlanVersionSummary[]>([])
const versionsLoading = ref(false)
const versionsError = ref('')
const showVersions = ref(false)
const mapErrors = ref<Record<string, boolean>>({})
const mealModal = ref<{ dayIndex: number; mealType: string; label: string } | null>(null)
const mealOptions = ref<MealSuggestion[]>([])
const mealAreasList = ref<MealArea[]>([])
const activeMealArea = ref<MealArea | null>(null)
const mealView = ref<'areas' | 'restaurants' | 'nearby'>('areas')
const mealBudgetMinutes = ref(0)
const mealTravelBudget = ref(0)
const mealLoading = ref(false)
const mealAreaQuery = ref('')
const mealAreaSearching = ref(false)
const mealAreaSearchError = ref('')
const nearbyQuery = ref('')
const nearbySearching = ref(false)
const nearbySearchError = ref('')
const mealAreaGroups = computed(() => {
  const groups = [
    { type: 'food_street', label: '美食街' },
    { type: 'mall', label: '商场 · 室内' },
    { type: 'neighborhood', label: '商圈' },
  ]
  return groups
    .map((group) => ({
      ...group,
      items: mealAreasList.value.filter((area) => area.area_type === group.type),
    }))
    .filter((group) => group.items.length > 0)
})
const mealError = ref('')
const mealChoices = ref<Record<string, MealSuggestion>>({})
const selectionsError = ref('')
const costUpdating = ref(false)
const costDirty = ref(false)
const costError = ref('')
const stays = ref<StaySuggestion[]>([])
const stayLoading = ref(false)
const stayError = ref('')
const selectedStay = ref<StaySuggestion | null>(null)
const stayQuery = ref('')
const staySearchResults = ref<StaySuggestion[]>([])
const staySearching = ref(false)
const staySearchError = ref('')
const staySearchActive = ref(false)
const visibleStays = computed(() =>
  staySearchActive.value ? staySearchResults.value : stays.value,
)
// 兴趣用 0–100 滑块表达强度；默认保留旧版“历史文化”优先的行为。
type InterestKey = 'history' | 'nature' | 'food'
const interestOptions: {
  key: InterestKey
  name: string
  desc: string
}[] = [
  { key: 'history', name: '历史文化', desc: '博物馆、古迹与城市记忆' },
  { key: 'nature', name: '自然风光', desc: '公园、山野与开阔视野' },
  { key: 'food', name: '本地美食', desc: '街巷、市场与餐桌故事' },
]
const interestValues = ref<Record<InterestKey, number>>({
  history: 80,
  nature: 0,
  food: 0,
})
// 0 最轻松、100 最充实；同时决定每日条目上限和行程缓冲。
const pace = ref(50)
const dailyItemLimit = computed(() =>
  pace.value <= 33 ? 2 : pace.value >= 72 ? 4 : 3,
)
const avoidTightSchedule = computed(() => pace.value < 67)
const paceLabel = computed(() =>
  pace.value <= 33 ? '轻松' : pace.value >= 72 ? '充实' : '适中',
)

const navItems: { id: View; label: string; hint: string }[] = [
  { id: 'overview', label: '总览', hint: 'Overview' },
  { id: 'create', label: '创建旅行', hint: 'New trip' },
  { id: 'plans', label: '我的方案', hint: 'Plans' },
  { id: 'stays', label: '住宿推荐', hint: 'Stays' },
]

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}

const destinationLabel = computed(() => destination.value || '未选择目的地')
// 单城市规划只需要目的地、日期、天数与预算；出发地仅保留为叙事字段。
const formReady = computed(() => Boolean(destination.value && startDate.value && budget.value && Number(days.value) > 0))
// 滚动量超过阈值即触发地球转向中国，之后不再随滚动改变
const transitionRequested = computed(() => scrollProgress.value > TRANSITION_TRIGGER)
// 第三页按滚动进度平滑进入：地图缩小左移、规划文字升起
const plannerProgress = computed(() => clamp01((scrollProgress.value - 0.5) / 0.5))
const plannerTextProgress = computed(() => clamp01((scrollProgress.value - 0.56) / 0.36))
const plannerOpacity = computed(() => plannerProgress.value)
const globeZoomProgress = computed(() => clamp01((focusProgress.value - ZOOM_START) / (1 - ZOOM_START)))
const globeScale = computed(() => 1 + globeZoomProgress.value * (GLOBE_ZOOM_SCALE - 1))
// 地球左移量：终态为自身宽度的 -16%（原先 -8%，按要求加倍）
const globeX = computed(() => focusProgress.value * -16)
// 放大过程中地球逐渐透明：开始放大时为 1，放大完成时刚好为 0，由中国地图无缝接管
const globeOpacity = computed(() => clamp01(1 - globeZoomProgress.value))
// 与地球淡出交叉溶解：进度 0.88→1 时地图由 0 淡入到 1，避免整块弹出
const atlasOpacity = computed(() => clamp01((focusProgress.value - 0.88) / 0.12))
// 地图默认居中铺满（第 1 页），第 2 页按实测位移缩小落到规划页左栏
const atlasStyle = computed(() => {
  const p = plannerProgress.value
  const { x, y, scale } = mapShift.value
  return {
    opacity: atlasOpacity.value,
    transform: `translate(${(x * p).toFixed(2)}px, ${(y * p).toFixed(2)}px) scale(${(1 + (scale - 1) * p).toFixed(4)})`,
  }
})
const storyPhase = computed<StoryPhase>(() => {
  if (plannerProgress.value > 0) return 'planner'
  if (!transitionRequested.value) return 'earth'
  if (focusProgress.value < 1) return 'focusing'
  return 'china-map'
})

function updateScrollProgress() {
  const story = storyRoot.value
  if (!story) return
  const range = Math.max(1, story.offsetHeight - window.innerHeight)
  scrollProgress.value = clamp01(-story.getBoundingClientRect().top / range)
}

/** 量出第三页左栏插槽的位置，换算成地图层需要平移与缩放多少 */
function measureMapSlot() {
  const slot = mapSlot.value
  const scene = plannerScene.value
  const wrap = document.querySelector('.china-map-wrap') as HTMLElement | null
  if (!slot || !scene || !wrap) return
  const slotRect = slot.getBoundingClientRect()
  const sceneRect = scene.getBoundingClientRect()
  // 滚到第三页时规划页顶部正好对齐视口顶部，因此相对偏移即那一刻的视口坐标
  const targetTop = slotRect.top - sceneRect.top
  const targetLeft = slotRect.left - sceneRect.left
  // offsetWidth / offsetHeight 不受 transform 影响，即地图的原始尺寸
  const baseWidth = wrap.offsetWidth || 1
  const baseHeight = wrap.offsetHeight || 1
  mapShift.value = {
    x: targetLeft + slotRect.width / 2 - window.innerWidth / 2,
    y: targetTop + slotRect.height / 2 - window.innerHeight / 2,
    // 等比缩放，保证地图完整落进插槽
    scale: Math.min(slotRect.width / baseWidth, slotRect.height / baseHeight),
  }
}

/** 滚轮分页：一次手势只切一页；过渡进行中或冷却期内忽略输入 */
function onWheel(event: WheelEvent) {
  if (activeView.value !== 'overview') return
  event.preventDefault()
  if (Math.abs(event.deltaY) < 4) return
  const now = performance.now()
  if (storyPhase.value === 'focusing' || now < wheelLockedUntil) return
  const from = Math.round(scrollProgress.value * (PAGE_COUNT - 1))
  const next = Math.min(PAGE_COUNT - 1, Math.max(0, from + (event.deltaY > 0 ? 1 : -1)))
  if (next === from) return
  wheelLockedUntil = now + WHEEL_COOLDOWN
  window.scrollTo({ top: next * window.innerHeight, behavior: 'smooth' })
}

/** 视口变化后重新测量插槽，并把滚动位置对齐回所在页 */
function handleResize() {
  measureMapSlot()
  const page = Math.round(scrollProgress.value * (PAGE_COUNT - 1))
  window.scrollTo({ top: page * window.innerHeight })
}

/** 滚动结束后对齐到最近的一页：键盘方向键、拖动滚动条也能落到整页 */
function handleScrollEnd() {
  if (activeView.value !== 'overview') return
  const page = Math.round(scrollProgress.value * (PAGE_COUNT - 1))
  const target = page * window.innerHeight
  if (Math.abs(window.scrollY - target) > 2) {
    window.scrollTo({ top: target })
  }
}

function buildInterests(): Record<string, number> {
  return Object.fromEntries(
    interestOptions.map((option) => [
      option.key,
      Math.round(interestValues.value[option.key]),
    ]),
  )
}

async function generatePlan(reuseTrip: boolean) {
  if (!formReady.value) {
    showBrief.value = true
    selectView('create')
    return
  }
  loading.value = true
  errorMessage.value = ''
  clearSelections()
  try {
    const city = destination.value.trim()
    const dayCount = Math.max(1, Math.min(30, Number(days.value) || 3))
    let currentTripId = tripId.value
    if (!reuseTrip || currentTripId === null) {
      const trip = await createTrip(city, `${city}${dayCount}日`)
      currentTripId = trip.id
      tripId.value = trip.id
    }
    plan.value = await createPlan(currentTripId, {
      city,
      start_date: startDate.value,
      days: dayCount,
      adults: Math.max(1, Number(travelers.value) || 1),
      children: 0,
      budget_total: Math.max(0, Number(budget.value) || 0),
      interests: buildInterests(),
      pace: pace.value,
      transport_preference: transportPreference.value,
      daily_start: '09:00',
      daily_end: '20:00',
      max_daily_items: dailyItemLimit.value,
      avoid_tight_schedule: avoidTightSchedule.value,
      max_walk_km: 8,
    })
    await loadSelections(plan.value.plan_id)
    selectView('plans')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '生成方案失败'
    selectView('plans')
  } finally {
    loading.value = false
  }
}

function beginPlanning() {
  void generatePlan(false)
}

function regeneratePlan() {
  void generatePlan(true)
}

async function refreshVersions(id: number | null = tripId.value) {
  if (id === null) {
    versions.value = []
    return
  }
  versionsLoading.value = true
  versionsError.value = ''
  try {
    const result = await listPlanVersions(id)
    versions.value = result.items
  } catch (error) {
    versionsError.value = error instanceof Error ? error.message : '读取版本历史失败'
  } finally {
    versionsLoading.value = false
  }
}

function toggleVersions() {
  showVersions.value = !showVersions.value
  if (showVersions.value) void refreshVersions()
}

async function openVersion(version: PlanVersionSummary) {
  versionsError.value = ''
  try {
    const loaded = await getPlanVersion(version.plan_id)
    plan.value = loaded
    tripId.value = loaded.trip_id
    await loadSelections(loaded.plan_id)
    showVersions.value = false
    selectView('plans')
  } catch (error) {
    versionsError.value = error instanceof Error ? error.message : '读取版本失败'
  }
}

async function removeVersion(version: PlanVersionSummary) {
  if (!window.confirm(`删除方案 v${version.version_no}？此操作不可撤销。`)) return
  versionsError.value = ''
  try {
    await deletePlanVersion(version.plan_id)
    if (plan.value?.plan_id === version.plan_id) {
      plan.value = null
      clearSelections()
      const remaining = versions.value.filter((item) => item.plan_id !== version.plan_id)
      if (remaining.length) await openVersion(remaining[remaining.length - 1])
    }
    await refreshVersions()
  } catch (error) {
    versionsError.value = error instanceof Error ? error.message : '删除版本失败'
  }
}

function versionTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function selectView(view: View) {
  activeView.value = view
  showBrief.value = false
  if (view === 'plans' && tripId.value !== null) void refreshVersions()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function navigate(view: View) {
  // 住宿页需要先取推荐；只切视图会停留在“没有返回住宿”的空状态。
  if (view === 'stays') {
    void openStays()
    return
  }
  selectView(view)
}

const planDateRange = computed(() => {
  if (!plan.value) return ''
  const last = plan.value.days[plan.value.days.length - 1]?.travel_date
  return last ? `${plan.value.start_date} → ${last}` : plan.value.start_date
})

function dayNumber(index: number): string {
  return String(index + 1).padStart(2, '0')
}

function formatMoney(value: number): string {
  return `¥${Math.round(value).toLocaleString('zh-CN')}`
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '耗时未知'
  const minutes = Math.max(1, Math.round(seconds / 60))
  return minutes >= 60 ? `${Math.floor(minutes / 60)}小时${minutes % 60}分` : `${minutes}分钟`
}

function formatDistance(meters: number | null): string {
  if (meters === null) return '距离未知'
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`
}

function modeLabel(mode: string): string {
  return ({ walk: '步行', active: '步行/骑行', transit: '公共交通总计', drive: '驾车', bicycle: '骑行' } as Record<string, string>)[mode] ?? mode
}

function legSummaryLabel(leg: RouteLegItem | null): string {
  if (!leg) return ''
  return leg.mode === 'transit' ? '公共交通总计' : modeLabel(leg.mode)
}

function stageLabel(index: number): string {
  return String.fromCharCode(0x2460 + index)
}

function walkWeatherHint(day: DayPlan): string {
  const weather = day.weather
  if (!weather || weather.status !== 'known') return ''
  if (!weather.risk_level || weather.risk_level === 'low') return ''
  return `${weather.condition ?? '天气'}，步行和骑行体验可能受影响`
}

function weatherText(day: { weather: PlanDetail['days'][number]['weather'] }): string {
  const weather = day.weather
  if (!weather || weather.status !== 'known') return '天气未知'
  const range = [weather.temperature_min, weather.temperature_max].filter((value) => value !== null)
  return `${weather.condition ?? '天气'}${range.length === 2 ? ` ${range[0]}–${range[1]}°C` : ''}`
}

function legFor(day: DayPlan, index: number): RouteLegItem | null {
  return day.legs[index] ?? null
}

function transitSegmentLabel(segment: TransitStep): string {
  if (segment.mode === 'walk') {
    const duration = segment.duration_s !== null ? ` · ${formatDuration(segment.duration_s)}` : ''
    const bike =
      segment.bike_duration_s !== null
        ? ` / 骑行 ${formatDuration(segment.bike_duration_s)}`
        : (segment.distance_m ?? 0) >= 300
          ? ' / 骑行未知'
          : ''
    return `步行 ${formatDistance(segment.distance_m)}${duration}${bike}`
  }
  const line = segment.line_name ?? (segment.mode === 'subway' ? '地铁' : '公交')
  const stops = segment.via_stops !== null ? ` · 经${segment.via_stops}站` : ''
  return `${line} · ${segment.departure_stop ?? '未知站'} → ${segment.arrival_stop ?? '未知站'}${stops}`
}

function legTimeLabel(leg: RouteLegItem | null): string {
  if (!leg) return ''
  if (leg.mode === 'active') {
    const parts: string[] = []
    if (leg.walk_duration_s != null) parts.push(`步行 ${formatDuration(leg.walk_duration_s)}`)
    if (leg.bike_duration_s != null) parts.push(`骑行 ${formatDuration(leg.bike_duration_s)}`)
    if (parts.length) return parts.join(' / ')
  }
  return formatDuration(leg.duration_s)
}

function legCostLabel(leg: RouteLegItem | null): string {
  if (!leg) return ''
  if (leg.mode === 'active') {
    if (leg.bike_cost_amount != null) {
      return `步行免费 / 骑行 ${formatMoney(leg.bike_cost_amount)}/人（估算）`
    }
    return '免费'
  }
  if (leg.cost_amount == null) return '费用未知'
  const suffix = leg.cost_basis === 'per_vehicle' ? '/车' : '/人'
  return `${formatMoney(leg.cost_amount)}${suffix}`
}

function legEstimateLabel(leg: RouteLegItem | null): string {
  if (!leg) return ''
  if (leg.status !== 'ok') return '回退估算'
  return leg.is_estimate ? '费用估算' : ''
}

function statusLabel(status: string): string {
  return ({ ok: '完整方案', partial: '部分日期为空', empty: '暂无可排景点' } as Record<string, string>)[status] ?? status
}

function costStatusLabel(status: string): string {
  return ({ confirmed: '已确认', quoted: '实时报价', estimated: '估算', partial: '部分未知', unknown: '待核' } as Record<string, string>)[status] ?? status
}

function costUpdatedLabel(value?: string | null): string {
  if (!value) return ''
  return `已按选择更新 ${new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

function stayPriceLabel(stay: StaySuggestion): string {
  if (stay.price_status === 'no_availability') return '该日期暂无可订房型'
  if (stay.price_status === 'not_found') return '未匹配到该酒店报价'
  if (stay.price_status === 'query_failed') return '查价失败，价格待核'
  return '价格待核'
}

function openingStatusLabel(item: PlanItem): string {
  if (item.opening_status === 'confirmed') return '开放时间已核'
  if (item.opening_status === 'estimated') return '开放时间估算'
  return item.opening_known ? '开放时间待核' : '开放时间未知'
}

function ticketStatusLabel(status?: string): string {
  return ({ confirmed: '已核', estimated: '估算', unknown: '待核' } as Record<string, string>)[status ?? 'unknown'] ?? '待核'
}

function itemTicketLabel(item: PlanItem): string {
  if (!item.ticket_status || item.ticket_status === 'unknown') return '票价待核'
  const price = item.ticket_price ?? item.estimated_cost
  return price === 0 ? '免费' : `${formatMoney(price)}/人`
}

function mealLabel(mealType: string): string {
  return mealType === 'lunch' ? '午餐' : '晚餐'
}

function mealChoiceKey(dayIndex: number, mealType: string): string {
  return `${dayIndex}-${mealType}`
}

function clearSelections() {
  mealChoices.value = {}
  selectedStay.value = null
  selectionsError.value = ''
  costDirty.value = false
  costError.value = ''
}

async function loadSelections(planId: number) {
  clearSelections()
  try {
    const saved = await getPlanSelections(planId)
    for (const meal of saved.meals) {
      mealChoices.value[mealChoiceKey(meal.day_index - 1, meal.meal_type)] = {
        name: meal.name,
        address: meal.address,
        distance_m: null,
        cost_amount: null,
        rating: null,
        travel_minutes: meal.travel_minutes,
        area_id: meal.area_id,
        area_name: null,
        quality_tag: null,
      }
    }
    if (saved.stay) {
      selectedStay.value = {
        name: saved.stay.name,
        address: saved.stay.address,
        business_area: saved.stay.business_area,
        stay_type: null,
        distance_m: null,
        avg_attraction_distance_m: null,
        avg_commute_minutes: null,
        max_commute_minutes: null,
        day_commutes: [],
        tier: saved.stay.tier,
        cost_amount: saved.stay.cost_amount,
        over_budget: false,
        price_status: saved.stay.price_status,
        price_source: saved.stay.price_source,
        price_checked_at: saved.stay.price_checked_at,
        price_note: saved.stay.price_note,
        rating: saved.stay.rating,
      }
    }
  } catch (error) {
    selectionsError.value = error instanceof Error ? error.message : '读取已保存选择失败'
  }
}

function selectionPayload(): PlanSelections {
  return {
    meals: Object.entries(mealChoices.value).map(([key, meal]) => {
      const [dayIndex, mealType] = key.split('-')
      return {
        day_index: Number(dayIndex) + 1,
        meal_type: mealType,
        name: meal.name,
        address: meal.address,
        area_id: meal.area_id,
        travel_minutes: meal.travel_minutes,
        cost_amount: meal.cost_amount,
      }
    }),
    stay: selectedStay.value
      ? {
          name: selectedStay.value.name,
          address: selectedStay.value.address,
          business_area: selectedStay.value.business_area,
          tier: selectedStay.value.tier,
          cost_amount: selectedStay.value.cost_amount,
          price_status: selectedStay.value.price_status,
          price_source: selectedStay.value.price_source,
          price_checked_at: selectedStay.value.price_checked_at,
          price_note: selectedStay.value.price_note,
          rating: selectedStay.value.rating,
        }
      : null,
  }
}

async function persistSelections() {
  if (!plan.value) return
  try {
    await savePlanSelections(plan.value.plan_id, selectionPayload())
    selectionsError.value = ''
  } catch (error) {
    selectionsError.value = error instanceof Error ? error.message : '保存选择失败'
  }
}

async function refreshCosts() {
  if (!plan.value) return
  costUpdating.value = true
  costError.value = ''
  try {
    await persistSelections()
    plan.value = await recalculatePlanCosts(plan.value.plan_id)
    costDirty.value = false
  } catch (error) {
    costError.value = error instanceof Error ? error.message : '更新花费失败'
  } finally {
    costUpdating.value = false
  }
}

async function openMealSuggestions(dayIndex: number, mealType: string) {
  if (!plan.value) return
  mealModal.value = { dayIndex, mealType, label: mealLabel(mealType) }
  mealAreasList.value = []
  mealOptions.value = []
  activeMealArea.value = null
  mealView.value = 'areas'
  mealError.value = ''
  nearbyQuery.value = ''
  nearbySearchError.value = ''
  mealLoading.value = true
  try {
    const result = await mealAreas(plan.value.plan_id, dayIndex + 1, mealType)
    mealAreasList.value = result.items
    mealBudgetMinutes.value = result.meal_budget_minutes
    mealTravelBudget.value = result.travel_budget_minutes
  } catch (error) {
    mealError.value = error instanceof Error ? error.message : '获取用餐区域失败'
  } finally {
    mealLoading.value = false
  }
  if (!mealError.value && mealAreasList.value.length === 0) {
    await loadNearbyMeals()
  }
}

async function selectMealArea(area: MealArea) {
  if (!plan.value || !mealModal.value) return
  activeMealArea.value = area
  mealView.value = 'restaurants'
  mealOptions.value = []
  mealAreaQuery.value = ''
  mealAreaSearchError.value = ''
  mealError.value = ''
  mealLoading.value = true
  try {
    const result = await mealAreaRestaurants(
      plan.value.plan_id,
      mealModal.value.dayIndex + 1,
      mealModal.value.mealType,
      area.id,
    )
    mealOptions.value = result.items
  } catch (error) {
    mealError.value = error instanceof Error ? error.message : '获取区域餐厅失败'
  } finally {
    mealLoading.value = false
  }
}

async function loadNearbyMeals() {
  if (!plan.value || !mealModal.value) return
  mealView.value = 'nearby'
  mealOptions.value = []
  mealError.value = ''
  nearbyQuery.value = ''
  nearbySearchError.value = ''
  mealLoading.value = true
  try {
    const result = await nearbyMeals(
      plan.value.plan_id,
      mealModal.value.dayIndex + 1,
      mealModal.value.mealType,
    )
    mealOptions.value = result.items
  } catch (error) {
    mealError.value = error instanceof Error ? error.message : '获取附近餐厅失败'
  } finally {
    mealLoading.value = false
  }
}

function backToMealAreas() {
  mealView.value = 'areas'
  activeMealArea.value = null
  mealOptions.value = []
  mealAreaQuery.value = ''
  mealAreaSearchError.value = ''
  nearbyQuery.value = ''
  nearbySearchError.value = ''
  mealError.value = ''
}

async function searchNearby() {
  if (!plan.value || !mealModal.value) return
  const query = nearbyQuery.value.trim()
  if (!query) return
  nearbySearching.value = true
  nearbySearchError.value = ''
  try {
    const result = await searchNearbyMeals(
      plan.value.plan_id,
      mealModal.value.dayIndex + 1,
      mealModal.value.mealType,
      query,
    )
    mealOptions.value = result.items
  } catch (error) {
    nearbySearchError.value = error instanceof Error ? error.message : '搜索附近餐厅失败'
  } finally {
    nearbySearching.value = false
  }
}

async function searchMealArea() {
  if (!plan.value || !mealModal.value || !activeMealArea.value) return
  const query = mealAreaQuery.value.trim()
  if (!query) return
  mealAreaSearching.value = true
  mealAreaSearchError.value = ''
  try {
    const result = await searchMealAreaRestaurants(
      plan.value.plan_id,
      mealModal.value.dayIndex + 1,
      mealModal.value.mealType,
      activeMealArea.value.id,
      query,
    )
    mealOptions.value = result.items
  } catch (error) {
    mealAreaSearchError.value = error instanceof Error ? error.message : '搜索餐厅失败'
  } finally {
    mealAreaSearching.value = false
  }
}

function chooseMeal(suggestion: MealSuggestion) {
  if (!mealModal.value) return
  const key = mealChoiceKey(mealModal.value.dayIndex, mealModal.value.mealType)
  mealChoices.value[key] = suggestion
  mealModal.value = null
  costDirty.value = true
  costError.value = ''
  void persistSelections()
}

function closeMealModal() {
  mealModal.value = null
}

async function openStays() {
  if (!plan.value) {
    selectView('create')
    return
  }
  selectView('stays')
  stayLoading.value = true
  stayError.value = ''
  stayQuery.value = ''
  staySearchResults.value = []
  staySearchActive.value = false
  staySearchError.value = ''
  staySearching.value = false
  try {
    const result = await staySuggestions(plan.value.plan_id)
    stays.value = result.items
  } catch (error) {
    stayError.value = error instanceof Error ? error.message : '获取住宿推荐失败'
  } finally {
    stayLoading.value = false
  }
}

function chooseStay(suggestion: StaySuggestion) {
  if (suggestion.price_status === 'no_availability') return
  selectedStay.value = suggestion
  costDirty.value = true
  costError.value = ''
  void persistSelections()
}

async function runStaySearch() {
  if (!plan.value) return
  const query = stayQuery.value.trim()
  if (!query) return
  staySearching.value = true
  staySearchError.value = ''
  staySearchActive.value = true
  try {
    const result = await searchStays(plan.value.plan_id, query)
    staySearchResults.value = result.items
  } catch (error) {
    staySearchError.value = error instanceof Error ? error.message : '搜索酒店失败'
    staySearchResults.value = []
  } finally {
    staySearching.value = false
  }
}

function clearStaySearch() {
  stayQuery.value = ''
  staySearchResults.value = []
  staySearchActive.value = false
  staySearchError.value = ''
}

function hideMap(planId: number, dayIndex: number) {
  mapErrors.value[`${planId}-${dayIndex}`] = true
}

function mapFailed(planId: number, dayIndex: number): boolean {
  return Boolean(mapErrors.value[`${planId}-${dayIndex}`])
}

onMounted(() => {
  // 先同步一次滚动状态：刷新时浏览器可能已恢复滚动位置
  updateScrollProgress()
  measureMapSlot()
  // 字体加载完成与布局稳定后再量一次，避免首次量到未定型的排版
  requestAnimationFrame(measureMapSlot)
  document.fonts?.ready.then(() => measureMapSlot()).catch(() => {})
  window.addEventListener('scroll', updateScrollProgress, { passive: true })
  // 需要 preventDefault 拦掉原生滚动，所以不能注册为 passive
  window.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('resize', handleResize)
  // 键盘方向键、拖动滚动条等原生滚动结束后，把位置对齐回整页
  window.addEventListener('scrollend', handleScrollEnd)
})
let bodyOverflowBeforeModal = ''
onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateScrollProgress)
  window.removeEventListener('wheel', onWheel)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('scrollend', handleScrollEnd)
  document.body.style.overflow = bodyOverflowBeforeModal
})

// 餐厅弹窗打开时锁住背景页面滚动，关闭后恢复原来的 overflow。
watch(mealModal, (value) => {
  if (value) {
    bodyOverflowBeforeModal = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = bodyOverflowBeforeModal
  }
})

// 回到前两页时重测插槽：此时规划页尚未展开，改目标不会造成跳动
watch(plannerProgress, (value) => {
  if (value === 0) measureMapSlot()
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-story': activeView === 'overview' }">
    <aside class="rail">
      <div class="brand-mark" aria-label="TravelMind">TM</div>
      <div class="rail-rule"></div>
      <nav class="rail-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.id"
          class="rail-item"
          :class="{ active: activeView === item.id }"
          type="button"
          @click="navigate(item.id)"
        >
          <span class="rail-icon" aria-hidden="true">{{ item.id === 'overview' ? '◌' : item.id === 'create' ? '↗' : '≋' }}</span>
          <span>{{ item.label }}</span>
          <small>{{ item.hint }}</small>
        </button>
      </nav>
      <div class="rail-footer">
        <span class="status-dot"></span>
        <span>国内版 · Demo</span>
      </div>
    </aside>

    <main class="main-stage">
      <header class="topbar">
        <div>
          <p class="eyebrow">TRAVEL PLANNING SYSTEM</p>
          <div class="top-title-row">
            <h1>把下一段路，想得更清楚。</h1>
            <span class="version-tag">MVP / 0.1</span>
          </div>
        </div>
        <div class="top-actions">
          <button class="icon-button" type="button" title="通知" aria-label="通知">⌁</button>
          <div class="avatar">旅</div>
        </div>
      </header>

      <section v-if="activeView === 'overview'" ref="storyRoot" class="story-view" :class="{ 'is-transitioning': storyPhase === 'focusing' }" :data-story-phase="storyPhase">
        <div class="story-progress"><span :style="{ transform: `scaleX(${scrollProgress})` }"></span></div>
        <section class="story-intro story-scene">
          <div class="scene-copy scene-copy-left"><p class="eyebrow">TRAVELMIND / 01</p><h2>世界很大，<br /><em>先找到你的方向。</em></h2><p class="scene-note">拖动这颗星球看看世界，向下滚动进入中国。</p></div>
          <div class="scroll-cue"><span></span><small>向下探索</small></div>
        </section>
        <div class="map-stage" aria-label="地球到中国地图的过渡预览">
          <div class="map-viewport globe-scene" :style="{ '--globe-scale': globeScale, '--globe-x': `${globeX}%`, opacity: globeOpacity }">
            <!-- 地球自行完成固定时长的转向，页面只接收动画进度。 -->
            <GlobeScene :transition-requested="transitionRequested" @transition-progress="focusProgress = $event" />
            <div class="map-caption">沉浸式路线预览</div>
            <div class="map-coordinates">39.9042° N<br />116.4074° E</div>
          </div>
          <div class="atlas-scene" :style="atlasStyle"><ChinaMapScene :interactive="storyPhase === 'china-map'" /><small :style="{ opacity: 1 - plannerProgress }">CHINA / DESTINATION FIELD</small></div>
        </div>

        <!-- 第二页占位：地图本体固定在 .map-stage 层里，不参与文档流 -->
        <div class="story-spacer" aria-hidden="true"></div>

        <section ref="plannerScene" class="planner-scene" :style="{ opacity: plannerOpacity }">
          <div ref="mapSlot" class="planner-map-slot" aria-hidden="true"><span>CHINA / ROUTE FIELD</span></div>
          <div class="planner-content" :style="{ transform: `translateY(${(1 - plannerTextProgress) * 36}px)` }"><div class="planner-copy"><p class="eyebrow">TRAVELMIND / 02</p><h2>现在，开始规划<em>你的那一条路。</em></h2><p>把目的地、日期和预算交给我们。地图会从远方回到你的行程。</p></div><div class="planner-form"><div class="form-line"><label>出发地<input v-model="origin" type="text" placeholder="例如：福州" /></label><span class="form-arrow">→</span><label>目的地<input v-model="destination" type="text" placeholder="例如：北京" /></label></div><div class="form-line form-line-small"><label>出发日期<input v-model="startDate" type="date" /></label><label>旅行天数<input v-model="days" min="1" max="10" type="number" /></label><label>同行人数<input v-model="travelers" min="1" type="number" /></label><label>总预算<input v-model="budget" type="number" placeholder="8000" /></label></div><button class="primary-action" :disabled="loading" type="button" @click="beginPlanning">{{ loading ? '正在生成…' : '开始规划' }} <span>→</span></button><p v-if="showBrief" class="form-warning">请先填写目的地、日期、天数和预算。</p></div></div>
        </section>
      </section>

      <section v-else-if="activeView === 'create'" class="content-view view-enter">
        <div class="content-header"><div><p class="section-kicker">TRIP BRIEF</p><h2>创建一段属于你的行程。</h2><p>先设定边界，规划器才知道什么值得被放进旅程。</p></div><span class="large-step">02</span></div>
        <div class="create-layout">
          <div class="long-form">
            <div class="form-section"><h3>路线与日期</h3><div class="form-row"><label class="field-block"><span>出发地</span><input v-model="origin" placeholder="例如：福州" /></label><label class="field-block"><span>目的地</span><input v-model="destination" placeholder="例如：北京" /></label></div><div class="form-row"><label class="field-block"><span>开始日期</span><input v-model="startDate" type="date" /></label><label class="field-block"><span>旅行天数</span><input v-model="days" min="1" max="10" type="number" /></label></div></div>
            <div class="form-section">
              <h3>兴趣与节奏</h3>
              <p class="slider-intro">拖动滑杆设置偏好强度：0 表示不作为偏好，100 表示优先安排。</p>
              <div class="slider-list">
                <label v-for="item in interestOptions" :key="item.key" class="slider-field">
                  <span class="slider-head"><strong>{{ item.name }}</strong><em>{{ item.desc }}</em><b>{{ interestValues[item.key] }}</b></span>
                  <input v-model.number="interestValues[item.key]" type="range" min="0" max="100" step="5" :aria-label="`${item.name}兴趣强度`" />
                </label>
              </div>
              <div class="slider-field pace-field">
                <span class="slider-head"><strong>旅行节奏</strong><em>{{ paceLabel }} · 每天约 {{ dailyItemLimit }} 个景点</em><b>{{ pace }}</b></span>
                <input v-model.number="pace" type="range" min="0" max="100" step="5" aria-label="旅行节奏" />
                <span class="slider-scale"><span>轻松</span><span>充实</span></span>
              </div>
            </div>
            <div class="form-section"><h3>预算与偏好</h3><div class="form-row"><label class="field-block"><span>总预算</span><input v-model="budget" type="number" placeholder="例如：8000" /></label><label class="field-block"><span>交通偏好</span><select v-model="transportPreference"><option value="auto">自动：近步行，远公交</option><option value="transit">优先公共交通</option><option value="walk">尽量步行</option><option value="drive">自驾出行</option><option value="bicycle">骑行</option></select></label></div></div>
            <button class="primary-action form-submit" :disabled="loading" type="button" @click="beginPlanning">{{ loading ? '正在生成…' : '生成旅行方案' }} <span>→</span></button>
          </div>
          <aside class="brief-aside"><div class="aside-mark">TM</div><h3>规划不是填满每一分钟。</h3><p>我们会把开放时间、距离、天气和预算放在同一张桌子上，再给你几种不同的答案。</p><div class="aside-rule"></div><span>当前版本</span><strong>国内旅行 · 数据预览</strong></aside>
        </div>
      </section>

      <section v-else-if="activeView === 'stays'" class="content-view stays-view view-enter">
        <div class="content-header">
          <div>
            <p class="section-kicker">WHERE TO STAY</p>
            <h2>住哪里，会改变每天的路线。</h2>
            <p>当前按整趟一家推荐，优先靠近行程中的景点；价格优先来自 RollingGo 实时查价，缺失时标待核，评分来自高德。</p>
          </div>
          <span class="large-step">04</span>
        </div>

        <div v-if="!plan" class="plan-state">
          <h3>先生成一条行程</h3>
          <p>住宿推荐需要先知道每天去哪些景点。</p>
          <button class="primary-action" type="button" @click="selectView('create')">去创建旅行 <span>→</span></button>
        </div>
        <div v-else-if="stayLoading" class="plan-state">
          <span class="loading-ring"></span>
          <h3>正在查找景点附近的住宿…</h3>
        </div>
        <div v-else-if="stayError" class="plan-state plan-error">
          <h3>住宿推荐没有加载成功</h3>
          <p>{{ stayError }}</p>
        </div>
        <template v-else>
          <p v-if="selectedStay" class="stay-saved">已保存选择：<strong>{{ selectedStay.name }}</strong>（随当前方案版本保存）</p>
          <form class="stay-search" @submit.prevent="runStaySearch">
            <input v-model="stayQuery" type="search" placeholder="输入任意酒店名、品牌或商圈，如 汉庭、国贸、王府井" />
            <button type="submit" :disabled="staySearching">搜索</button>
            <button v-if="staySearchActive" type="button" class="stay-search-clear" @click="clearStaySearch">清除</button>
          </form>
          <p v-if="staySearchError" class="stay-search-error">{{ staySearchError }}</p>
          <div v-if="staySearching" class="plan-state">
            <span class="loading-ring"></span>
            <h3>正在搜索酒店…</h3>
          </div>
          <div v-else-if="visibleStays.length === 0" class="plan-state">
            <h3>{{ staySearchActive ? '没有找到匹配的酒店' : '附近没有返回住宿' }}</h3>
            <p>{{ staySearchActive ? '换一个品牌名或关键词试试。' : '可以稍后重试，或先按行程区域自行选择。' }}</p>
          </div>
          <div v-else class="stay-grid">
            <article
              v-for="stay in visibleStays"
              :key="stay.name"
              class="stay-card"
              :class="{ selected: selectedStay?.name === stay.name }"
            >
              <div class="stay-card-head">
                <span class="stay-area">{{ stay.business_area ?? '区域未知' }}</span>
                <span v-if="selectedStay?.name === stay.name" class="stay-selected">已选择</span>
                <span v-else-if="stay.tier" class="stay-tier">{{ stay.tier }}</span>
              </div>
              <h3>{{ stay.name }}</h3>
              <p>{{ stay.address ?? '地址未知' }}</p>
              <div class="stay-metrics">
                <span>日均通勤 {{ stay.avg_commute_minutes !== null ? `${stay.avg_commute_minutes} 分钟` : '未知' }}</span>
                <span>单日最长 {{ stay.max_commute_minutes !== null ? `${stay.max_commute_minutes} 分钟` : '未知' }}</span>
                <span v-if="stay.day_commutes.length">分天：{{ stay.day_commutes.map((value, index) => `第${index + 1}天 ${value} 分钟`).join(' · ') }}</span>
                <span v-if="stay.cost_amount !== null">参考价 {{ formatMoney(stay.cost_amount) }}/晚<small v-if="stay.price_status === 'quoted'" class="price-source">实时价</small><small v-if="stay.over_budget" class="price-over">超预算</small></span>
                <span v-else class="price-unavailable">{{ stayPriceLabel(stay) }}</span>
                <span v-if="stay.price_note" class="price-note" :title="stay.price_note">{{ stay.price_note }}</span>
                <span>评分 {{ stay.rating ?? '未知' }}</span>
              </div>
              <button type="button" class="stay-button" :disabled="stay.price_status === 'no_availability'" @click="chooseStay(stay)">
                {{ stay.price_status === 'no_availability' ? '暂无可订' : selectedStay?.name === stay.name ? '已选择这家' : '选择这家' }}
              </button>
            </article>
          </div>
          <p class="stay-note">{{ staySearchActive ? '搜索结果仍按每天首尾通勤排序；RollingGo 查不到实时价时标“待核”。' : '先按高德综合热度取前 25 家，再过滤低评分/超预算/纯宾馆，最后按每天首尾通勤排序；价格由 RollingGo 按入住日期查询，查不到标“待核”；当前整趟只选一家，暂不做订房。' }}</p>
        </template>
      </section>

      <section v-else class="content-view plans-view view-enter">
        <div class="content-header">
          <div>
            <p class="section-kicker">YOUR ROUTES</p>
            <h2 v-if="plan">{{ plan.city }}，{{ plan.days_count }} 天，{{ planDateRange }}</h2>
            <h2 v-else>{{ destinationLabel }}，{{ loading ? '正在规划…' : '还在等你确认。' }}</h2>
            <p v-if="plan">方案 v{{ plan.version_no }} · {{ statusLabel(plan.status) }} · 路线与天气来自高德</p>
            <p v-else>填写目的地、日期和预算，生成一条包含真实路线、天气和步行距离的行程。</p>
          </div>
          <span class="large-step">03</span>
        </div>

        <div v-if="loading" class="plan-state">
          <span class="loading-ring"></span>
          <h3>正在查询路线和天气…</h3>
          <p>高德路线需要逐段计算；失败的路段会标为未知，不会用直线距离冒充。</p>
        </div>

        <div v-else-if="errorMessage" class="plan-state plan-error">
          <span class="empty-symbol">!</span>
          <h3>方案没有生成</h3>
          <p>{{ errorMessage }}</p>
          <button class="primary-action" type="button" @click="selectView('create')">返回修改条件 <span>→</span></button>
        </div>

        <template v-else-if="plan">
          <div class="plan-summary">
            <div><span>预计费用</span><strong>{{ plan.total_estimated_cost > 0 ? formatMoney(plan.total_estimated_cost) : '待补全' }}</strong></div>
            <div><span>预算差额</span><strong :class="{ negative: plan.budget_difference < 0 }">{{ plan.budget_total > 0 ? formatMoney(plan.budget_difference) : '未设置' }}</strong></div>
            <div><span>天气</span><strong>{{ plan.weather_known ? '已取到预报' : '部分/未知' }}</strong></div>
            <div><span>版本</span><strong>v{{ plan.version_no }}</strong></div>
          </div>
          <div v-if="plan.costs" class="cost-breakdown">
            <span><em>门票</em>{{ formatMoney(plan.costs.tickets_amount) }}<small>{{ costStatusLabel(plan.costs.tickets_status) }} · 已确认 {{ formatMoney(plan.costs.tickets_confirmed_amount) }} / 估算 {{ formatMoney(plan.costs.tickets_estimated_amount) }}</small><small v-if="plan.costs.tickets_unknown_count">另有 {{ plan.costs.tickets_unknown_count }} 项待核</small></span>
            <span><em>市内交通</em>{{ formatMoney(plan.costs.transport_amount) }}<small>{{ costStatusLabel(plan.costs.transport_status) }}</small></span>
            <span><em>餐饮</em>{{ formatMoney(plan.costs.meals_amount) }}<small>{{ costStatusLabel(plan.costs.meals_status) }}</small></span>
            <span><em>住宿</em>{{ formatMoney(plan.costs.lodging_amount) }}<small>{{ costStatusLabel(plan.costs.lodging_status) }}</small></span>
            <span v-if="!plan.costs.budget_complete" class="cost-warning">费用未完整：{{ plan.costs.unknown_items.join('；') }}</span>
            <span v-if="costDirty" class="cost-warning">已选餐厅/酒店，花费待更新</span>
            <span v-if="plan.costs.updated_at" class="cost-updated">{{ costUpdatedLabel(plan.costs.updated_at) }}</span>
            <span v-if="costError" class="cost-warning">{{ costError }}</span>
          </div>
          <div class="plan-toolbar">
            <span>{{ selectionsError || '餐厅/住宿选择会随当前版本保存；改条件只新增版本，不覆盖旧版本。' }}</span>
            <div class="plan-toolbar-actions">
              <button type="button" class="cost-refresh" :class="{ pending: costDirty }" :disabled="costUpdating" @click="refreshCosts">{{ costUpdating ? '更新中…' : '更新花销' }}</button>
              <button type="button" @click="toggleVersions">{{ showVersions ? '收起版本' : '版本历史' }}</button>
              <button type="button" @click="openStays">住宿推荐</button>
              <button type="button" :disabled="loading" @click="regeneratePlan">重新生成</button>
            </div>
          </div>

          <section v-if="showVersions" class="version-panel">
            <header class="version-head">
              <div>
                <p class="section-kicker">VERSION HISTORY</p>
                <h3>方案版本</h3>
              </div>
              <button type="button" class="version-close" @click="showVersions = false">×</button>
            </header>
            <p v-if="versionsLoading" class="version-state">正在读取版本…</p>
            <p v-else-if="versionsError" class="version-state version-error">{{ versionsError }}</p>
            <p v-else-if="versions.length === 0" class="version-state">还没有保存的版本。</p>
            <div v-else class="version-list">
              <article
                v-for="version in versions"
                :key="version.plan_id"
                class="version-row"
                :class="{ current: plan.plan_id === version.plan_id }"
              >
                <div class="version-main">
                  <strong>v{{ version.version_no }}</strong>
                  <span v-if="plan.plan_id === version.plan_id" class="version-current">当前</span>
                  <span class="version-status">{{ statusLabel(version.status) }}</span>
                </div>
                <div class="version-meta">
                  <span>{{ version.start_date }} · {{ version.days }} 天 · {{ version.adults + version.children }} 人</span>
                  <span>{{ formatMoney(version.total_estimated_cost) }} · 生成于 {{ versionTime(version.generated_at) }}</span>
                </div>
                <div class="version-actions">
                  <button type="button" @click="openVersion(version)">查看</button>
                  <button type="button" class="version-delete" @click="removeVersion(version)">删除</button>
                </div>
              </article>
            </div>
          </section>

          <article v-for="(day, dayIndex) in plan.days" :key="day.travel_date" class="day-card">
            <header class="day-head">
              <div>
                <span class="day-index">DAY {{ dayNumber(dayIndex) }}</span>
                <h3>{{ day.travel_date }}</h3>
              </div>
              <div class="day-meta">
                <span>{{ weatherText(day) }}</span>
                <span v-if="walkWeatherHint(day)" class="weather-walk-hint">{{ walkWeatherHint(day) }}</span>
                <span>{{ day.walk_km !== null ? `步行 ${day.walk_km} km` : '步行距离未知' }}</span>
                <span>{{ day.estimated_cost > 0 ? `人均门票 ${formatMoney(day.estimated_cost)}` : '门票待补全' }}</span>
              </div>
            </header>
            <div class="day-body">
              <div class="day-map">
                <img
                  v-if="!mapFailed(plan.plan_id, dayIndex + 1)"
                  :src="planMapUrl(plan.plan_id, dayIndex + 1)"
                  :alt="`${day.travel_date} 的 1→2→3 路线图`"
                  @error="hideMap(plan.plan_id, dayIndex + 1)"
                />
                <div v-else class="map-fallback">静态图暂不可用，按左侧顺序浏览</div>
              </div>
              <ol class="day-items">
                <template v-for="(item, itemIndex) in day.items" :key="item.poi_id">
                  <li class="item-row">
                    <span class="item-order">{{ item.order }}</span>
                    <div class="item-main">
                      <strong>{{ item.name }}</strong>
                      <span>{{ item.start_time.slice(0, 5) }}–{{ item.end_time.slice(0, 5) }} · {{ openingStatusLabel(item) }}</span>
                    </div>
                    <span class="item-cost">{{ itemTicketLabel(item) }}<small>{{ ticketStatusLabel(item.ticket_status) }}</small></span>
                  </li>
                  <li v-if="legFor(day, itemIndex)" class="leg-row" :class="{ failed: legFor(day, itemIndex)?.status !== 'ok' }">
                    <span class="leg-line"></span>
                    <div class="leg-content">
                      <div class="leg-summary">
                        <span>{{ legSummaryLabel(legFor(day, itemIndex)) }} · {{ formatDistance(legFor(day, itemIndex)?.distance_m ?? null) }} · {{ legTimeLabel(legFor(day, itemIndex)) }} · {{ legCostLabel(legFor(day, itemIndex)) }}</span>
                        <span v-if="legEstimateLabel(legFor(day, itemIndex))" class="leg-flag">{{ legEstimateLabel(legFor(day, itemIndex)) }}</span>
                      </div>
                      <div v-if="legFor(day, itemIndex)?.segments.length" class="leg-transit">
                        <span v-for="(segment, segmentIndex) in legFor(day, itemIndex)?.segments" :key="segmentIndex" class="transit-step" :class="segment.mode">
                          <span class="transit-index">{{ stageLabel(segmentIndex) }}</span>
                          <span>{{ transitSegmentLabel(segment) }}</span>
                        </span>
                      </div>
                    </div>
                  </li>
                </template>
                <li v-if="day.items.length === 0" class="empty-day">当天没有可安排景点</li>
              </ol>
            </div>
            <div v-if="day.meals.length" class="meal-list">
              <div v-for="meal in day.meals" :key="meal.meal_type" class="meal-row">
                <span class="meal-time">{{ meal.start_time.slice(0, 5) }}–{{ meal.end_time.slice(0, 5) }}</span>
                <div class="meal-main">
                  <strong>{{ mealLabel(meal.meal_type) }}</strong>
                  <span>已预留 {{ meal.duration_minutes }} 分钟</span>
                  <span v-if="mealChoices[mealChoiceKey(dayIndex, meal.meal_type)]" class="meal-choice">
                    已选：{{ mealChoices[mealChoiceKey(dayIndex, meal.meal_type)].name }}
                  </span>
                </div>
                <button type="button" class="meal-button" @click="openMealSuggestions(dayIndex, meal.meal_type)">推荐餐厅</button>
              </div>
            </div>
          </article>

          <section v-if="plan.notes.length" class="plan-notes">
            <h3>需要知道的边界</h3>
            <ul>
              <li v-for="note in plan.notes" :key="note">{{ note }}</li>
            </ul>
          </section>
        </template>

        <div v-else class="plan-empty-layout">
          <div class="empty-map"><div class="empty-map-grid"></div><div class="empty-route-line"></div><span class="empty-pin one"></span><span class="empty-pin two"></span><div class="empty-label">ROUTE PREVIEW</div></div>
          <div class="empty-copy"><span class="empty-symbol">◎</span><h3>还没有生成方案</h3><p>填写目的地、日期和预算，TravelMind 会生成一条带真实路线、天气和步行距离的行程。</p><button class="primary-action" type="button" @click="selectView('create')">返回填写需求 <span>→</span></button><div class="plan-types"><span>真实路线</span><span>近 4 天天气</span><span>步行上限</span><span>版本保存</span></div></div>
        </div>
      </section>

      <div v-if="mealModal" class="meal-backdrop">
        <div class="meal-modal">
          <header class="meal-modal-head">
            <div class="meal-modal-title">
              <button v-if="mealView !== 'areas'" type="button" class="meal-back" @click="backToMealAreas">←</button>
              <div>
                <p class="section-kicker">MEAL SUGGESTIONS</p>
                <h3>
                  {{ mealModal.label }}
                  <template v-if="mealView === 'areas'">用餐区域</template>
                  <template v-else-if="mealView === 'nearby'">附近其他</template>
                  <template v-else>· {{ activeMealArea?.name }}</template>
                </h3>
                <p v-if="mealView === 'areas'" class="meal-budget-hint">
                  总预算 {{ mealBudgetMinutes }} 分钟 · 交通不超过 {{ mealTravelBudget }} 分钟
                </p>
              </div>
            </div>
            <button type="button" class="meal-close" @click="closeMealModal">×</button>
          </header>
          <div v-if="mealLoading" class="meal-modal-state">正在按实际路线时间筛选…</div>
          <div v-else-if="mealError" class="meal-modal-state">{{ mealError }}</div>
          <template v-else-if="mealView === 'areas'">
            <div v-if="mealAreasList.length === 0" class="meal-modal-state">
              没有区域满足当前用餐时间预算，下面看看附近其他餐厅。
            </div>
            <div v-else class="meal-area-groups">
              <div v-for="group in mealAreaGroups" :key="group.type" class="meal-area-group">
                <h4>{{ group.label }}</h4>
                <div class="meal-areas">
                  <button v-for="area in group.items" :key="area.id" type="button" class="meal-area" @click="selectMealArea(area)">
                    <div class="meal-area-head">
                      <strong>{{ area.name }}</strong>
                      <span class="meal-area-time">交通约 {{ area.travel_minutes }} 分钟</span>
                    </div>
                    <small>
                      区域热度 {{ Math.round(area.popularity * 100) }}
                      <template v-if="area.weather_friendly"> · 室内，雨天/高温友好</template>
                      · {{ area.note ?? '含区域步行' }}
                    </small>
                  </button>
                </div>
              </div>
            </div>
            <button type="button" class="meal-nearby-button" @click="loadNearbyMeals">
              附近其他 · 不进入热门区域，按实际路线时间排序
            </button>
          </template>
          <template v-else>
            <form v-if="mealView === 'restaurants'" class="meal-area-search" @submit.prevent="searchMealArea">
              <input v-model="mealAreaQuery" type="search" :placeholder="`在${activeMealArea?.name ?? '当前区域'}内搜索餐厅，如烤鸭、火锅、小吃`" />
              <button type="submit" :disabled="mealAreaSearching">搜索</button>
            </form>
            <form v-else-if="mealView === 'nearby'" class="meal-area-search" @submit.prevent="searchNearby">
              <input v-model="nearbyQuery" type="search" placeholder="在附近其他中搜索，如烤鸭、火锅、小吃" />
              <button type="submit" :disabled="nearbySearching">搜索</button>
            </form>
            <p v-if="mealAreaSearchError" class="meal-search-error">{{ mealAreaSearchError }}</p>
            <p v-if="nearbySearchError" class="meal-search-error">{{ nearbySearchError }}</p>
            <div v-if="mealAreaSearching || nearbySearching" class="meal-modal-state">正在搜索…</div>
            <div v-else-if="mealOptions.length === 0" class="meal-modal-state">没有满足时间预算的餐厅</div>
            <div v-else class="meal-options">
              <button v-for="suggestion in mealOptions" :key="`${suggestion.name}-${suggestion.address}`" type="button" class="meal-option" @click="chooseMeal(suggestion)">
                <strong>
                  {{ suggestion.name }}
                  <span v-if="suggestion.quality_tag" class="meal-quality">{{ suggestion.quality_tag }}</span>
                </strong>
                <span>{{ suggestion.address ?? '地址未知' }}</span>
                <small>
                  步行 {{ suggestion.distance_m !== null ? `${suggestion.distance_m} m` : '距离未知' }}
                  <template v-if="suggestion.travel_minutes !== null"> · 交通约 {{ suggestion.travel_minutes }} 分钟</template>
                  · 人均 {{ suggestion.cost_amount !== null ? formatMoney(suggestion.cost_amount) : '待核' }}
                  · 评分 {{ suggestion.rating ?? '未知' }}
                </small>
              </button>
            </div>
          </template>
          <p class="meal-modal-note">推荐只用于选择，不提供订座；人气只参与排序，实际路线时间决定是否进入推荐。</p>
        </div>
      </div>
    </main>
  </div>
</template>
