// 系统接口（开发文档 §7.8）。
//
// 覆盖 /health、/ready 与 /meta/* 三组只读接口。

import { api } from '@/api/client'
import type { HotlinePayload, MetaConfig, ReadyReport } from '@/api/types'

export interface HealthPayload {
  status: string
  service: string
  env: string
}

export const systemApi = {
  // GET /health —— 存活探针，只证明进程活着
  health: () => api.get<HealthPayload>('/health'),

  // GET /ready —— 依赖就绪探针。
  //
  // deep=true 时后端会真实请求一次 LLM，用于确认模型服务可达；
  // 默认只做廉价检查，避免每次探针都产生调用费用。
  //
  // 注意：degraded 不等于失败。本机没起 Redis 与 Chroma 时这两项就是 degraded，
  // 界面要区分展示，而不是一律飘红。
  ready: (deep = false) => api.get<ReadyReport>(`/ready${deep ? '?deep=1' : ''}`),

  // GET /meta/hotlines —— 求助资源。
  //
  // 返回里的 verified_at 是最近一次人工核实日期，
  // 界面应把"号码可能变动"这条提示一起展示出来。
  hotlines: (region?: string) =>
    api.get<HotlinePayload>(`/meta/hotlines${region ? `?region=${region}` : ''}`),

  // GET /meta/config —— 前端可见配置。
  //
  // 注册页的 consent_version 必须从这里取。写死版本号会导致免责声明升级后
  // 注册永久失败：前端让用户同意 v1.0，后端却在校验 v2.0。
  metaConfig: () => api.get<MetaConfig>('/meta/config'),

}

