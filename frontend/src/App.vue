<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GlobeScene from './components/GlobeScene.vue'
import ChinaMapScene from './components/ChinaMapScene.vue'
import { createPlan, createTrip, mealSuggestions, planMapUrl, staySuggestions, type MealSuggestion, type PlanDetail, type StaySuggestion } from './api'

type DayPlan = PlanDetail['days'][number]
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
const mapErrors = ref<Record<string, boolean>>({})
const mealModal = ref<{ dayIndex: number; mealType: string; label: string } | null>(null)
const mealOptions = ref<MealSuggestion[]>([])
const mealLoading = ref(false)
const mealError = ref('')
const mealChoices = ref<Record<string, MealSuggestion>>({})
const stays = ref<StaySuggestion[]>([])
const stayLoading = ref(false)
const stayError = ref('')
const selectedStay = ref<StaySuggestion | null>(null)
// 旅行偏好（你的节奏）：多选，默认选中第一项
const preferences = ref<string[]>(['历史文化'])
const preferenceOptions = [
  { name: '历史文化', desc: '博物馆、古迹与城市记忆' },
  { name: '自然风光', desc: '公园、山野与开阔视野' },
  { name: '本地美食', desc: '街巷、市场与餐桌故事' },
  { name: '慢一点', desc: '每天留出真正的余地' },
]

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

/** 切换旅行偏好（多选） */
function togglePreference(name: string) {
  preferences.value = preferences.value.includes(name)
    ? preferences.value.filter((item) => item !== name)
    : [...preferences.value, name]
}

function buildInterests(): Record<string, number> {
  const tagMap: Record<string, string> = {
    历史文化: 'history',
    自然风光: 'nature',
    本地美食: 'food',
  }
  const interests: Record<string, number> = {}
  for (const preference of preferences.value) {
    const tag = tagMap[preference]
    if (tag) interests[tag] = 80
  }
  return Object.keys(interests).length ? interests : { history: 50 }
}

async function generatePlan(reuseTrip: boolean) {
  if (!formReady.value) {
    showBrief.value = true
    selectView('create')
    return
  }
  loading.value = true
  errorMessage.value = ''
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
      pace: preferences.value.includes('慢一点') ? 30 : 65,
      transport_preference: transportPreference.value,
      daily_start: '09:00',
      daily_end: '20:00',
      max_daily_items: 3,
      max_walk_km: 8,
    })
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

function selectView(view: View) {
  activeView.value = view
  showBrief.value = false
  window.scrollTo({ top: 0, behavior: 'smooth' })
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
  return ({ confirmed: '已确认', estimated: '估算', partial: '部分未知', unknown: '待核' } as Record<string, string>)[status] ?? status
}

function mealLabel(mealType: string): string {
  return mealType === 'lunch' ? '午餐' : '晚餐'
}

function mealChoiceKey(dayIndex: number, mealType: string): string {
  return `${dayIndex}-${mealType}`
}

async function openMealSuggestions(dayIndex: number, mealType: string) {
  if (!plan.value) return
  mealModal.value = { dayIndex, mealType, label: mealLabel(mealType) }
  mealOptions.value = []
  mealError.value = ''
  mealLoading.value = true
  try {
    const result = await mealSuggestions(plan.value.plan_id, dayIndex + 1, mealType)
    mealOptions.value = result.items
  } catch (error) {
    mealError.value = error instanceof Error ? error.message : '获取餐厅失败'
  } finally {
    mealLoading.value = false
  }
}

function chooseMeal(suggestion: MealSuggestion) {
  if (!mealModal.value) return
  const key = mealChoiceKey(mealModal.value.dayIndex, mealModal.value.mealType)
  mealChoices.value[key] = suggestion
  mealModal.value = null
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
  selectedStay.value = suggestion
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
          @click="selectView(item.id)"
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
            <div class="form-section"><h3>你的节奏</h3><div class="preference-grid"><button v-for="item in preferenceOptions" :key="item.name" class="preference" :class="{ active: preferences.includes(item.name) }" type="button" :aria-pressed="preferences.includes(item.name)" @click="togglePreference(item.name)"><strong>{{ item.name }}</strong><span>{{ item.desc }}</span></button></div></div>
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
            <p>当前按整趟一家推荐，优先靠近行程中的景点；价格和评分来自高德，可能缺失。</p>
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
          <div v-if="stays.length === 0" class="plan-state">
            <h3>附近没有返回住宿</h3>
            <p>可以稍后重试，或先按行程区域自行选择。</p>
          </div>
          <div v-else class="stay-grid">
            <article
              v-for="stay in stays"
              :key="stay.name"
              class="stay-card"
              :class="{ selected: selectedStay?.name === stay.name }"
            >
              <div class="stay-card-head">
                <span class="stay-area">{{ stay.business_area ?? '区域未知' }}</span>
                <span v-if="selectedStay?.name === stay.name" class="stay-selected">已选择</span>
              </div>
              <h3>{{ stay.name }}</h3>
              <p>{{ stay.address ?? '地址未知' }}</p>
              <div class="stay-metrics">
                <span>到景点平均 {{ stay.avg_attraction_distance_m !== null ? formatDistance(stay.avg_attraction_distance_m) : '未知' }}</span>
                <span>参考价 {{ stay.cost_amount !== null ? `${formatMoney(stay.cost_amount)}/晚` : '待核' }}</span>
                <span>评分 {{ stay.rating ?? '未知' }}</span>
              </div>
              <button type="button" class="stay-button" @click="chooseStay(stay)">
                {{ selectedStay?.name === stay.name ? '已选择这家' : '选择这家' }}
              </button>
            </article>
          </div>
          <p class="stay-note">当前整趟只选一家住宿；数据结构和页面按“可扩展为多晚/多酒店”设计，暂不做订房。</p>
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
            <span><em>门票</em>{{ formatMoney(plan.costs.tickets_amount) }}<small>{{ costStatusLabel(plan.costs.tickets_status) }}</small></span>
            <span><em>市内交通</em>{{ formatMoney(plan.costs.transport_amount) }}<small>{{ costStatusLabel(plan.costs.transport_status) }}</small></span>
            <span><em>餐饮</em>{{ formatMoney(plan.costs.meals_amount) }}<small>{{ costStatusLabel(plan.costs.meals_status) }}</small></span>
            <span><em>住宿</em>{{ formatMoney(plan.costs.lodging_amount) }}<small>{{ costStatusLabel(plan.costs.lodging_status) }}</small></span>
            <span v-if="!plan.costs.budget_complete" class="cost-warning">费用未完整：{{ plan.costs.unknown_items.join('；') }}</span>
          </div>
          <div class="plan-toolbar">
            <span>生成后已自动保存为版本；改条件只会新增版本，不覆盖旧版本。</span>
            <div class="plan-toolbar-actions">
              <button type="button" @click="openStays">住宿推荐</button>
              <button type="button" :disabled="loading" @click="regeneratePlan">重新生成</button>
            </div>
          </div>

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
                <span>{{ day.estimated_cost > 0 ? formatMoney(day.estimated_cost) : '费用待补全' }}</span>
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
                      <span>{{ item.start_time.slice(0, 5) }}–{{ item.end_time.slice(0, 5) }} · {{ item.opening_known ? '开放时间已核' : '开放时间待核' }}</span>
                    </div>
                    <span class="item-cost">{{ item.estimated_cost > 0 ? formatMoney(item.estimated_cost) : '票价待核' }}</span>
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
            <div>
              <p class="section-kicker">MEAL SUGGESTIONS</p>
              <h3>{{ mealModal.label }}推荐 · 附近餐厅</h3>
            </div>
            <button type="button" class="meal-close" @click="closeMealModal">×</button>
          </header>
          <div v-if="mealLoading" class="meal-modal-state">正在查询附近餐厅…</div>
          <div v-else-if="mealError" class="meal-modal-state">{{ mealError }}</div>
          <div v-else-if="mealOptions.length === 0" class="meal-modal-state">附近暂时没有返回餐厅</div>
          <div v-else class="meal-options">
            <button v-for="suggestion in mealOptions" :key="suggestion.name" type="button" class="meal-option" @click="chooseMeal(suggestion)">
              <strong>{{ suggestion.name }}</strong>
              <span>{{ suggestion.address ?? '地址未知' }}</span>
              <small>
                步行 {{ suggestion.distance_m !== null ? `${suggestion.distance_m} m` : '距离未知' }}
                · 人均 {{ suggestion.cost_amount !== null ? formatMoney(suggestion.cost_amount) : '待核' }}
                · 评分 {{ suggestion.rating ?? '未知' }}
              </small>
            </button>
          </div>
          <p class="meal-modal-note">推荐只用于选择，不提供订座；营业时间和价格请以商家为准。</p>
        </div>
      </div>
    </main>
  </div>
</template>
