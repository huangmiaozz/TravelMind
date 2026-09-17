<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import chinaGeoJson from 'china-geojson'

type ChinaFeature = {
  type: 'Feature'
  properties?: { id?: string; name?: string }
  geometry: unknown
}

type ChinaGeoJsonModule = { China: { type: 'FeatureCollection'; features: ChinaFeature[] } }
const container = ref<HTMLDivElement | null>(null)
const props = withDefaults(defineProps<{ interactive?: boolean }>(), { interactive: true })
let chart: echarts.ECharts | null = null
let china: ChinaGeoJsonModule['China']
const currentRegion = ref('中国')
const canGoBack = ref(false)

function registerAndRender(regionName = '中国') {
  if (!chart) return

  const feature = china.features.find((item) => item.properties?.name === regionName)
  const mapName = regionName === '中国' ? 'china' : `region-${feature?.properties?.id ?? regionName}`
  const mapData = feature ? { type: 'FeatureCollection', features: [feature] } : china

  echarts.registerMap(mapName, mapData as echarts.GeoJSONSource)
  currentRegion.value = regionName
  canGoBack.value = Boolean(feature)
  chart.clear()
  chart.setOption({
    animationDuration: 700,
    backgroundColor: 'transparent',
    geo: {
      map: mapName,
      roam: false,
      silent: false,
      selectedMode: false,
      itemStyle: {
        areaColor: 'rgba(18, 96, 120, .28)',
        borderColor: '#63d9da',
        borderWidth: regionName === '中国' ? 1 : 1.3,
      },
      emphasis: { itemStyle: { areaColor: 'rgba(99, 217, 218, .52)' } },
    },
    series: [{
      type: 'scatter',
      coordinateSystem: 'geo',
      data: regionName === '中国'
        ? [
            { name: '北京', value: [116.4, 39.9, 1] },
            { name: '福州', value: [119.3, 26.1, 1] },
          ]
        : [],
      symbolSize: 9,
      itemStyle: { color: '#f3bd65', shadowBlur: 18, shadowColor: '#f3bd65' },
    }],
  })
}

function handleMapClick(params: { name?: string }) {
  if (!props.interactive || currentRegion.value !== '中国' || !params.name) return
  registerAndRender(params.name)
}

function goBack() {
  registerAndRender()
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  if (!container.value) return

  china = (chinaGeoJson as ChinaGeoJsonModule).China
  chart = echarts.init(container.value, undefined, { renderer: 'svg' })
  chart.on('click', handleMapClick)
  registerAndRender()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.off('click', handleMapClick)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="china-map-wrap">
    <div v-if="props.interactive" class="china-map-toolbar" :class="{ 'is-national': !canGoBack }">
      <button v-if="canGoBack" type="button" class="china-map-back" aria-label="返回中国地图" @click="goBack">← 全国</button>
      <span>{{ currentRegion === '中国' ? '全国目的地' : `${currentRegion} · 省域地图` }}</span>
      <small v-if="!canGoBack">点击省份进入下一级</small>
    </div>
    <div ref="container" class="china-map-scene-container" aria-label="可下钻的中国目的地地图"></div>
  </div>
</template>
