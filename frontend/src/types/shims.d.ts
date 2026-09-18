/**
 * 补充声明：以下包本身不提供类型，DefinitelyTyped 中也没有对应的 @types 包。
 * 这里只声明项目实际用到的成员，而不是整包声明为 any —— 这样拼错导出名仍会报错。
 */

declare module 'topojson-client' {
  /**
   * 把 TopoJSON 拓扑中的指定对象转换为 GeoJSON。
   *
   * 实际返回值是 GeoJSON `Feature` 或 `FeatureCollection`，取决于传入的是单个
   * geometry 还是 geometry collection。因为调用方需要按具体类型使用，
   * 这里返回 `unknown`，由调用处自行断言。
   */
  export function feature(topology: unknown, object: unknown): unknown
}

declare module 'china-geojson' {
  /** 省级行政区 GeoJSON 中的一个 feature */
  export interface ChinaFeature {
    type: 'Feature'
    properties?: { id?: string; name?: string }
    geometry: unknown
  }

  /** 省级行政区集合，features 约 37 个省级单位；无市级数据 */
  export type ChinaGeoJson = {
    type: 'FeatureCollection'
    features: ChinaFeature[]
  }

  /** 该包的默认导出只包含一个 China 键 */
  const chinaGeoJson: { China: ChinaGeoJson }
  export default chinaGeoJson
}
