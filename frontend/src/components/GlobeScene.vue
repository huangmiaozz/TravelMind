<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import earthFlyLine from 'earth-flyline'
import { feature } from 'topojson-client'
import worldTopology from 'world-atlas/countries-110m.json'

/**
 * ===== 库内机制实测标准数据（earth-flyline@1.6.9，请勿凭印象修改）=====
 *
 * 1. 摄像机（ChartScene.createOrthographicCamera / createCamera）
 *    库默认 cameraType = "OrthographicCamera"：
 *      camera.position = (0, 0, 500)，camera.lookAt(0, 0, 0)
 *      → “正对镜头”方向 = (0, 0, 1)，镜头俯仰 0°，镜头水平方位角 90°
 *    只有显式传入 cameraType = "PerspectiveCamera" 时才是：
 *      camera.position = (350, 350, 350)
 *      → 方向 = normalize(1, 1, 1)，镜头俯仰 35.264°，镜头水平方位角 45°
 *    踩坑记录：曾误按透视相机数据做定位，导致画面恒定偏 45°（水平）与 35.264°（俯仰），
 *    表现为“只横向转动、纵向完全没对齐”。因此下方改为运行时从真实摄像机推导。
 *
 * 2. 经纬度 → 球面坐标（库内 utils 的 lon2xyz）
 *    lon2xyz(R, lon, lat) 内部先对经度取负，展开后等价于：
 *      x = R·cos(lat)·cos(lon)
 *      y = R·sin(lat)
 *      z = -R·cos(lat)·sin(lon)
 *    由此推出：任意点的水平角 β = atan2(z, x) = -lon，俯仰角 λ = lat
 *
 * 3. 转盘模型（本组件采用的旋转模型）
 *    姿态固定写成 Q = Rx(pitch) · Ry(yaw)，由此可推出屏幕中心点满足：
 *      中心点纬度 = pitch + 镜头俯仰
 *      中心点经度 = -镜头方位角 - yaw
 *    因此把 pitch 限制在纬度 ±90° 以内，就等于“地球永远不会转过南北极”。
 *    注意必须保持这个乘序：换成先俯仰再偏航会引入滚转，两极附近就会出现方向反转。
 *    拖拽松手后按角速度继续滑行，每帧以 exp(-INERTIA_DAMPING × dt) 衰减（与帧率无关）；
 *    纵向滑行顶到极点会立即停止，不会在极点空转。
 *
 * 4. 定位公式（让指定经纬度对准屏幕中心）
 *    yaw   = -镜头方位角 - lon
 *    pitch = lat - 镜头俯仰
 *    实测（正交相机 camAzimuth = 90°、锚点 104°E / 36°N）：yaw = -194.00°，pitch = +36.00°
 *
 * 5. 为什么不用库内置拖拽（踩坑记录）
 *    库内 EarthController 用 rotateX()（局部轴）搭配 rotateOnWorldAxis(Y)（世界轴），
 *    纵向转过极点后局部 X 轴会翻转，导致所有方向的拖拽一起反向，且它没有任何角度限制参数。
 *    因此这里把 dragConfig 的 disableX / disableY 都设为 true，拖拽改由本组件自己实现。
 *    另：过渡期间容器是 pointer-events: none，若拖拽途中进入过渡则收不到 mouseup，
 *    库内 isDragging 会残留为 true（表现为之后“不按键也跟手旋转”），故过渡开始时必须清零。
 *
 * 6. 浏览器实测的过渡终态
 *    旋转在 focusProgress = 0.65 处完成，之后只做放大；
 *    终态地球 scale = 1.5（150%）、地球 opacity 0、中国地图 opacity 1 接管；
 *    滚回顶部后地球恢复 scale 1 与初始姿态。
 */

// 复用的向量与四元数类型：直接使用库内 three 的四元数实例，避免额外引入 three 依赖
type Vec3 = { x: number; y: number; z: number }
type QuatLike = {
  x: number
  y: number
  z: number
  w: number
  clone(): QuatLike
  copy(q: QuatLike): QuatLike
  set(x: number, y: number, z: number, w: number): QuatLike
  premultiply(q: QuatLike): QuatLike
}

// 世界坐标系的 Y 轴（屏幕竖直方向）与 X 轴（屏幕水平方向）
const WORLD_Y: Vec3 = { x: 0, y: 1, z: 0 }
const WORLD_X: Vec3 = { x: 1, y: 0, z: 0 }
// 镜头参考角：由 syncCameraFrame() 依据库内真实摄像机写入
// 默认（正交相机 position(0,0,500)）下为：方位角 90°、俯仰 0°
let camAzimuth = Math.PI / 2
let camElevation = 0
// 转盘模型下“屏幕中心点”的纬度上限：锁在 ±90°，因此永远不会越过南北极
const MAX_LATITUDE = Math.PI / 2
// 中国居中锚点（经纬度），调整它与第二页地图的对齐关系
// 实测：该点就是旋转结束后屏幕正中心的那个点
const CHINA_ANCHOR = { lon: 104, lat: 36 }
// 旋转定位在总进度中的占比，其余进度留给放大
const ROTATE_END = 0.65
// 整段过渡的固定时长（秒），与滚动速度完全无关
const TRANSITION_DURATION = 1.6
// 拖拽灵敏度的兜底值（弧度/像素），正常情况下按地球在屏幕上的半径实时计算
const FALLBACK_RAD_PER_PIXEL = 0.005
// 松手后滑行的阻尼系数（每秒指数衰减，数值越大停得越快）
const INERTIA_DAMPING = 4.5
// 滑行角速度上限（弧度/秒），避免快速甩动导致旋转失控
const MAX_SPIN = 6
// 松手前若已停顿超过这个时长（秒），就不产生滑行
const INERTIA_IDLE_THRESHOLD = 0.1
// 角速度平滑系数，抑制单帧抖动带来的乱滑
const SPIN_SMOOTHING = 0.4

function clampSpin(velocity: number) {
  return Math.min(MAX_SPIN, Math.max(-MAX_SPIN, velocity))
}

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3)
}

function toRadians(degrees: number) {
  return (degrees * Math.PI) / 180
}

/** 把角度归一化到 (-π, π]，避免偏航角无限累加 */
function normalizeAngle(angle: number) {
  const twoPi = Math.PI * 2
  let value = angle % twoPi
  if (value > Math.PI) value -= twoPi
  if (value <= -Math.PI) value += twoPi
  return value
}

/** 限制屏幕中心点纬度，使其不会越过南北极 */
function clampLatitude(latitude: number) {
  return Math.min(MAX_LATITUDE, Math.max(-MAX_LATITUDE, latitude))
}

const container = ref<HTMLDivElement | null>(null)
// 向下滚动触发聚焦中国，向上滚动回到第一屏初始姿态
const props = defineProps<{ transitionRequested?: boolean }>()
// 回传 0→1 的过渡进度，供页面控制放大与地图替换
const emit = defineEmits<{ transitionProgress: [value: number] }>()
let chart: ReturnType<typeof earthFlyLine.init> | null = null
let animationFrame = 0
let lastFrameTime = 0
// 过渡进度：0 为第一屏，1 为已定位并放大到中国
let focusProgress = 0
// —— 转盘模型状态 ——
// 屏幕中心点经度 = -camAzimuth - viewYaw，纬度 = viewPitch + camElevation
// viewYaw 可无限水平旋转；viewPitch 经 clampLatitude 限制，因此永远不会越过南北极
let viewYaw = 0
let viewPitch = 0
// 第一屏初始姿态：库中 mainContainer 初始为单位四元数，对应 yaw / pitch 均为 0
const INITIAL_YAW = 0
const INITIAL_PITCH = 0
// 当前这一段过渡的动画状态
let legActive = false
let legElapsed = 0
let legDuration = TRANSITION_DURATION
let legFromProgress = 0
let legToProgress = 0
let legFromYaw = 0
let legFromPitch = 0
let legToYaw = 0
let legToPitch = 0
// 拖拽状态
let dragActive = false
let dragLastX = 0
let dragLastY = 0
let radPerPixel = FALLBACK_RAD_PER_PIXEL
// 拖拽角速度（弧度/秒），松手后按此速度继续滑行并逐帧衰减
let yawVelocity = 0
let pitchVelocity = 0
let dragLastTime = 0

/** 取出地球容器当前的姿态四元数 */
function mainQuaternion(): QuatLike {
  return chart!.mainContainer.quaternion as unknown as QuatLike
}

/** 绕指定轴构造四元数 */
function axisAngleQuaternion(axis: Vec3, angle: number): QuatLike {
  const half = angle / 2
  const sin = Math.sin(half)
  return mainQuaternion().clone().set(axis.x * sin, axis.y * sin, axis.z * sin, Math.cos(half))
}

/** 把当前的 yaw / pitch 写入地球姿态：Q = Rx(pitch) · Ry(yaw) */
function applyViewOrientation() {
  const orientation = axisAngleQuaternion(WORLD_Y, viewYaw)
  orientation.premultiply(axisAngleQuaternion(WORLD_X, viewPitch))
  mainQuaternion().copy(orientation)
}

/**
 * 依据库内真实摄像机推导镜头参考角。
 * 摄像机始终 lookAt(0,0,0)，故“从原点指向摄像机”的方向就是正对镜头的方向。
 * 实测：默认正交相机得到方位角 90°、俯仰 0°；改用透视相机则是 45° / 35.264°。
 */
function syncCameraFrame() {
  const position = chart!.camera.position
  const length = Math.hypot(position.x, position.y, position.z) || 1
  const direction = { x: position.x / length, y: position.y / length, z: position.z / length }
  camElevation = Math.asin(Math.min(1, Math.max(-1, direction.y)))
  camAzimuth = Math.atan2(direction.z, direction.x)
}

/**
 * 让指定经纬线对准屏幕中心所需的角度。
 * 库内 lon2xyz 先对经度取负，因此点的水平角 β = -lon；屏幕中心的水平角等于镜头方位角，
 * 于是中心点经度 = -camAzimuth - yaw，即 yaw = -camAzimuth - lon。
 * 实测（camAzimuth = 90°、锚点 104°E）：yaw = -90° - 104° = -194°，与实测值一致。
 */
function orientationFor(lon: number, lat: number) {
  return {
    yaw: normalizeAngle(-camAzimuth - toRadians(lon)),
    pitch: clampLatitude(toRadians(lat) - camElevation),
  }
}

/**
 * 兜底清理库内拖拽控制器的状态。
 * 我们把 dragConfig 的 disableX / disableY 都设为 true，库不会再旋转地球，
 * 但它的 mousedown 仍会把 isDragging 置为 true；若此时容器被设为 pointer-events: none，
 * mouseup 不会送达画布，标记就会残留。这里统一清零，避免出现“不按键也跟手旋转”。
 */
function resetLibraryDragState() {
  const controls = chart?.controls as unknown as
    | { isDragging?: boolean; rotationVelocity?: { x: number; y: number } }
    | undefined
  if (!controls) return
  controls.isDragging = false
  if (controls.rotationVelocity) {
    controls.rotationVelocity.x = 0
    controls.rotationVelocity.y = 0
  }
}

/** 开始拖拽：按地球在屏幕上的半径换算灵敏度，实现“表面跟手” */
function startDrag(event: MouseEvent) {
  if (!chart || legActive || !container.value) return
  dragActive = true
  dragLastX = event.clientX
  dragLastY = event.clientY
  dragLastTime = performance.now()
  // 重新按下时清掉上一次的滑行，避免两次操作叠加
  yawVelocity = 0
  pitchVelocity = 0
  // 正交相机垂直半高为 200 个世界单位、地球半径 150，故屏幕半径 = 0.375 × 容器高度
  const rect = container.value.getBoundingClientRect()
  radPerPixel = 1 / Math.max(1, rect.height * 0.375)
  window.addEventListener('mousemove', moveDrag)
  window.addEventListener('mouseup', endDrag)
}

function moveDrag(event: MouseEvent) {
  if (!dragActive) return
  const dx = event.clientX - dragLastX
  const dy = event.clientY - dragLastY
  dragLastX = event.clientX
  dragLastY = event.clientY
  const now = performance.now()
  // 单帧时间下限取 1/240 秒，避免极短时间间隔算出爆表的角速度
  const elapsed = Math.max((now - dragLastTime) / 1000, 1 / 240)
  dragLastTime = now

  const deltaYaw = dx * radPerPixel
  const deltaPitch = dy * radPerPixel
  // 向右拖动 → 屏幕中心点向西移动（经度减小）；向下拖动 → 中心点纬度增大
  // 纬度每次都做钳制，拖到南北极就停住，不会翻过去造成方向反转
  viewYaw = normalizeAngle(viewYaw + deltaYaw)
  viewPitch = clampLatitude(viewPitch + deltaPitch)
  applyViewOrientation()

  // 平滑记录角速度，供松手后的滑行使用
  yawVelocity = yawVelocity * (1 - SPIN_SMOOTHING) + (deltaYaw / elapsed) * SPIN_SMOOTHING
  pitchVelocity = pitchVelocity * (1 - SPIN_SMOOTHING) + (deltaPitch / elapsed) * SPIN_SMOOTHING
}

/** 结束拖拽：监听挂在 window 上，指针移出画布也能正常收尾 */
function endDrag() {
  if (!dragActive) return
  dragActive = false
  window.removeEventListener('mousemove', moveDrag)
  window.removeEventListener('mouseup', endDrag)
  // 松手前若已经停住（例如按住不动再松开），就不该继续滑行
  if ((performance.now() - dragLastTime) / 1000 > INERTIA_IDLE_THRESHOLD) {
    yawVelocity = 0
    pitchVelocity = 0
    return
  }
  // 限制最大滑行速度，避免快速甩动导致旋转失控
  yawVelocity = clampSpin(yawVelocity)
  pitchVelocity = clampSpin(pitchVelocity)
}

/** 松手后的滑行：按时间指数衰减，并对纬度继续做极点钳制 */
function applyInertia(delta: number) {
  if (dragActive || legActive) return
  if (Math.abs(yawVelocity) < 1e-4 && Math.abs(pitchVelocity) < 1e-4) {
    yawVelocity = 0
    pitchVelocity = 0
    return
  }

  viewYaw = normalizeAngle(viewYaw + yawVelocity * delta)
  const nextPitch = clampLatitude(viewPitch + pitchVelocity * delta)
  // 已经顶在极点且仍往外推时，直接停掉纵向滑行，避免在极点“空转”
  if (nextPitch === viewPitch && pitchVelocity !== 0) pitchVelocity = 0
  else viewPitch = nextPitch
  applyViewOrientation()

  // 与帧率无关的指数衰减
  const decay = Math.exp(-INERTIA_DAMPING * delta)
  yawVelocity *= decay
  pitchVelocity *= decay
}

/** 启动一段过渡：正向定位到中国，或反向回到第一屏初始姿态 */
function startLeg(targetProgress: number) {
  if (!chart) return
  const from = focusProgress
  if (Math.abs(targetProgress - from) < 0.001) return

  // 过渡期间禁止一切操作，同时结束可能进行中的拖拽并清掉库内残留状态
  endDrag()
  resetLibraryDragState()
  // 过渡由时间线驱动，期间不做滑行，速度直接清零
  yawVelocity = 0
  pitchVelocity = 0
  legFromProgress = from
  legToProgress = targetProgress
  legElapsed = 0
  // 时长按剩余距离缩放，中途反向也不会突兀
  legDuration = Math.max(0.2, TRANSITION_DURATION * Math.abs(targetProgress - from))
  legFromYaw = viewYaw
  legFromPitch = viewPitch
  if (targetProgress > from) {
    const goal = orientationFor(CHINA_ANCHOR.lon, CHINA_ANCHOR.lat)
    // 偏航走最短路径，避免绕远路多转一圈
    legToYaw = legFromYaw + normalizeAngle(goal.yaw - legFromYaw)
    legToPitch = goal.pitch
  } else {
    legToYaw = legFromYaw + normalizeAngle(INITIAL_YAW - legFromYaw)
    legToPitch = INITIAL_PITCH
  }
  legActive = true
}

function animateFocus() {
  animationFrame = window.requestAnimationFrame(animateFocus)
  if (!chart) return

  const now = performance.now()
  const delta = lastFrameTime ? Math.min((now - lastFrameTime) / 1000, 0.05) : 0
  lastFrameTime = now
  if (!legActive) {
    // 没有过渡在进行时，继续处理松手后的滑行
    applyInertia(delta)
    return
  }

  legElapsed = Math.min(legDuration, legElapsed + delta)
  const linear = legElapsed / legDuration
  focusProgress = legFromProgress + (legToProgress - legFromProgress) * linear
  // 前 ROTATE_END 段完成旋转定位，剩余进度用于放大
  const travel = Math.abs(legToProgress - legFromProgress) * ROTATE_END
  const rotateT = travel > 0 ? Math.min(1, Math.abs(focusProgress - legFromProgress) / travel) : 1
  const eased = easeOutCubic(rotateT)
  viewYaw = legFromYaw + (legToYaw - legFromYaw) * eased
  // 纬度全程经过钳制，过渡过程中也不会掠过极点
  viewPitch = clampLatitude(legFromPitch + (legToPitch - legFromPitch) * eased)
  applyViewOrientation()
  emit('transitionProgress', focusProgress)

  if (legElapsed >= legDuration) {
    legActive = false
    focusProgress = legToProgress
    viewYaw = normalizeAngle(legToYaw)
    viewPitch = legToPitch
    applyViewOrientation()
    emit('transitionProgress', focusProgress)
  }
}

onMounted(() => {
  if (!container.value) return

  const worldGeoJson = feature(worldTopology as never, worldTopology.objects.countries as never) as never
  earthFlyLine.registerMap('world', worldGeoJson)
  chart = earthFlyLine.init({
    dom: container.value,
    map: 'world',
    // 取消库内自转：旋转完全交给用户拖拽与本组件的过渡动画
    // 库默认 options.autoRotate = true、options.rotateSpeed = 0.01，两者都不再使用
    autoRotate: false,
    mode: '3d',
    // 保留库内置控制器实例，但把它的旋转完全关掉（见下方 dragConfig），改由本组件接管拖拽。
    // 原因：库内用 rotateX()（局部轴）与 rotateOnWorldAxis(Y)（世界轴）混用，纵向转过极点后
    // 局部 X 轴会翻转，导致所有方向的拖拽都反向，且无法限制角度，因此不复用它的旋转逻辑。
    // 仅当 enableZoom !== false 时库才会额外创建 OrbitControls，此处关闭缩放，不会有第二套控制器。
    controls: 'custom',
    config: {
      R: 150,
      enableZoom: false,
      // config 在 Store.setConfig 中是深合并（merge({}, 默认配置, 传入配置)），
      // 因此下面只写需要覆盖的字段，未写的会保留官方默认值
      // 官方蔚蓝主题
      bgStyle: { color: '#040D21', opacity: 0 },
      mapStyle: { areaColor: '#013e87', lineColor: '#516aaf' },
      spriteStyle: { color: '#138cdf', show: true },
      pathStyle: { color: '#7aaae9' },
      flyLineStyle: { color: '#02fff6' },
      scatterStyle: { color: '#02fff6' },
      earth: {
        // 库默认 rotationSpeed 1 / inertiaFactor 0.95 / disableX true / disableY false。
        // 这里两个方向都设为 true，并清零速度与惯性，让库内 EarthController 完全不参与旋转，
        // 旋转改由本组件的转盘模型接管，从而可以限制纬度、锁住南北极。
        dragConfig: {
          rotationSpeed: 0,
          inertiaFactor: 0,
          disableX: true,
          disableY: true,
        },
      },
    },
  })
  // 透明清屏：需与 config.bgStyle 的 color/opacity 保持一致，否则画布会出现可见的矩形底色
  chart.renderer.setClearColor('#040D21', 0)
  // 从库内真实摄像机同步镜头参考角，避免假设相机类型与位置
  syncCameraFrame()
  // 第一屏姿态即 yaw / pitch 均为 0，与库中 mainContainer 的初始单位四元数一致
  applyViewOrientation()
  // 拖拽改为手动监听，库内控制器的旋转已关闭
  container.value.addEventListener('mousedown', startDrag)
  animateFocus()

  chart.addData('flyLine', [
    { from: { id: 'fuzhou', lon: 119.3, lat: 26.1 }, to: { id: 'beijing', lon: 116.4, lat: 39.9 } },
  ])
})

onBeforeUnmount(() => {
  container.value?.removeEventListener('mousedown', startDrag)
  endDrag()
  window.cancelAnimationFrame(animationFrame)
  chart?.destroy?.()
  chart = null
})

watch(() => props.transitionRequested, (requested) => startLeg(requested ? 1 : 0))
</script>

<template>
  <div ref="container" class="globe-scene-container" aria-label="3D 地球与路线预览"></div>
</template>
