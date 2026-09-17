<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GlobeScene from './components/GlobeScene.vue'
import ChinaMapScene from './components/ChinaMapScene.vue'

type View = 'overview' | 'create' | 'plans'
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
const budget = ref('')
const showBrief = ref(false)
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
]

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}

const destinationLabel = computed(() => destination.value || '未选择目的地')
const formReady = computed(() => Boolean(origin.value && destination.value && startDate.value && budget.value))
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

function beginPlanning() {
  if (!formReady.value) {
    showBrief.value = true
    selectView('create')
    return
  }
  selectView('plans')
}

function selectView(view: View) {
  activeView.value = view
  showBrief.value = false
  window.scrollTo({ top: view === 'overview' ? 0 : document.body.scrollHeight, behavior: 'smooth' })
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
onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateScrollProgress)
  window.removeEventListener('wheel', onWheel)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('scrollend', handleScrollEnd)
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
          <div class="planner-content" :style="{ transform: `translateY(${(1 - plannerTextProgress) * 36}px)` }"><div class="planner-copy"><p class="eyebrow">TRAVELMIND / 02</p><h2>现在，开始规划<em>你的那一条路。</em></h2><p>把目的地、日期和预算交给我们。地图会从远方回到你的行程。</p></div><div class="planner-form"><div class="form-line"><label>出发地<input v-model="origin" type="text" placeholder="例如：福州" /></label><span class="form-arrow">→</span><label>目的地<input v-model="destination" type="text" placeholder="例如：北京" /></label></div><div class="form-line form-line-small"><label>出发日期<input v-model="startDate" type="date" /></label><label>同行人数<input v-model="travelers" min="1" type="number" /></label><label>总预算<input v-model="budget" type="number" placeholder="8000" /></label></div><button class="primary-action" type="button" @click="beginPlanning">开始规划 <span>→</span></button><p v-if="showBrief" class="form-warning">请先填写出发地、目的地、日期和预算。</p></div></div>
        </section>
      </section>

      <section v-else-if="activeView === 'create'" class="content-view view-enter">
        <div class="content-header"><div><p class="section-kicker">TRIP BRIEF</p><h2>创建一段属于你的行程。</h2><p>先设定边界，规划器才知道什么值得被放进旅程。</p></div><span class="large-step">02</span></div>
        <div class="create-layout">
          <div class="long-form">
            <div class="form-section"><h3>路线与日期</h3><div class="form-row"><label class="field-block"><span>出发地</span><input v-model="origin" placeholder="例如：福州" /></label><label class="field-block"><span>目的地</span><input v-model="destination" placeholder="例如：北京" /></label></div><div class="form-row"><label class="field-block"><span>开始日期</span><input v-model="startDate" type="date" /></label><label class="field-block"><span>旅行天数</span><input value="5" type="number" /></label></div></div>
            <div class="form-section"><h3>你的节奏</h3><div class="preference-grid"><button v-for="item in preferenceOptions" :key="item.name" class="preference" :class="{ active: preferences.includes(item.name) }" type="button" :aria-pressed="preferences.includes(item.name)" @click="togglePreference(item.name)"><strong>{{ item.name }}</strong><span>{{ item.desc }}</span></button></div></div>
            <div class="form-section"><h3>预算与偏好</h3><div class="form-row"><label class="field-block"><span>总预算</span><input v-model="budget" type="number" placeholder="例如：8000" /></label><label class="field-block"><span>交通偏好</span><select><option>优先公共交通</option><option>舒适优先</option><option>自驾出行</option></select></label></div></div>
            <button class="primary-action form-submit" type="button" @click="beginPlanning">生成旅行方案 <span>→</span></button>
          </div>
          <aside class="brief-aside"><div class="aside-mark">TM</div><h3>规划不是填满每一分钟。</h3><p>我们会把开放时间、距离、天气和预算放在同一张桌子上，再给你几种不同的答案。</p><div class="aside-rule"></div><span>当前版本</span><strong>国内旅行 · 数据预览</strong></aside>
        </div>
      </section>

      <section v-else class="content-view plans-view view-enter">
        <div class="content-header"><div><p class="section-kicker">YOUR ROUTES</p><h2>{{ destinationLabel }}，还在等你确认。</h2><p>这是结果页的视觉预览，接入 Planner 后这里会出现可比较的真实方案。</p></div><span class="large-step">03</span></div>
        <div class="plan-empty-layout"><div class="empty-map"><div class="empty-map-grid"></div><div class="empty-route-line"></div><span class="empty-pin one"></span><span class="empty-pin two"></span><div class="empty-label">ROUTE PREVIEW</div></div><div class="empty-copy"><span class="empty-symbol">◎</span><h3>还没有生成方案</h3><p>填写出发地、目的地、日期和预算，TravelMind 会为你准备几条不同取向的路线。</p><button class="primary-action" type="button" @click="selectView('create')">返回填写需求 <span>→</span></button><div class="plan-types"><span>综合最优</span><span>更省钱</span><span>更舒适</span><span>兴趣优先</span></div></div></div>
      </section>
    </main>
  </div>
</template>
