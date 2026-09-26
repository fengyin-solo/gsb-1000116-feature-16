<template>
  <section class="page" data-module="audit">
    <header class="page-head">
      <div>
        <h2>内审管理管理</h2>
        <p class="page-desc">维护内审记录，围绕内审编号、审核范围、审核组长、审核日期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记内审记录</button>
        <button class="btn" type="button" @click="exportRows">导出内审管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>内审编号</span>
        <input v-model="filters.keyword" placeholder="按内审编号检索" />
      </label>
      <label class="filter-item">
        <span>审核范围</span>
        <input v-model="filters.scope" placeholder="按审核范围检索" />
      </label>
      <label class="filter-item">
        <span>审核组长</span>
        <input v-model="filters.leader" placeholder="按审核组长检索" />
      </label>
      <label class="filter-item">
        <span>内审状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit" :disabled="loading">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody v-if="loading">
        <tr>
          <td :colspan="columns.length + 1" class="empty-state">正在加载内审记录…</td>
        </tr>
      </tbody>
      <tbody v-else-if="loadError">
        <tr>
          <td :colspan="columns.length + 1" class="empty-state">
            <p class="error-text">{{ loadError }}</p>
            <button class="btn" type="button" @click="reload">重试</button>
          </td>
        </tr>
      </tbody>
      <tbody v-else>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <template v-if="hasActiveFilters">
              <p>没有符合当前筛选条件的内审记录，可调整条件后重新查询。</p>
              <button class="btn" type="button" @click="resetFilters">重置条件</button>
            </template>
            <template v-else-if="page > 1">
              <p>第 {{ page }} 页没有数据：记录总数可能已变化，当前共 {{ total }} 条。</p>
              <button class="btn" type="button" @click="goPage(1)">回到第一页</button>
            </template>
            <template v-else>
              <p>暂无内审记录：首次使用或记录尚未登记，可先登记内审记录；如果刚刚操作过，也可以重试加载。</p>
              <button class="btn" type="button" @click="reload">重试</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条内审管理记录<template v-if="total > 0">，第 {{ page }} / {{ pageCount }} 页</template></span>
      <span class="pager">
        <button class="btn" type="button" :disabled="loading || page <= 1" @click="goPage(page - 1)">上一页</button>
        <button class="btn" type="button" :disabled="loading || page >= pageCount" @click="goPage(page + 1)">下一页</button>
        <select v-model.number="size" :disabled="loading" @change="changePageSize">
          <option v-for="option in pageSizes" :key="option" :value="option">每页 {{ option }} 条</option>
        </select>
      </span>
      <span v-if="feedback" :class="feedbackIsError ? 'error-text' : 'feedback-ok'">{{ feedback }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { extractErrorDetail, fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stat = { label: string; value: number }

const ENDPOINT = '/api/audit'
const columns = ["内审编号", "审核范围", "审核组长", "审核日期", "不符合项", "纠正期限", "跟踪验证", "内审状态"]
const actions = ["开始内审", "完成内审", "跟踪验证"]
const statuses = ["计划中", "执行中", "已完成", "跟踪中"]
// 单页上限 200 与后端 MAX_PAGE_SIZE 保持一致，达到上限时后端会给出可读说明
const pageSizes = [20, 50, 100, 200]
const statLabels = ["记录总数", "计划内审", "进行中内审", "待跟踪内审"]

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const loading = ref(true)
const loadError = ref('')
const feedback = ref('')
const feedbackIsError = ref(false)
const stats = ref<Stat[]>(zeroStats())
const filters = ref({ keyword: '', scope: '', leader: '', status: '' })

const hasActiveFilters = computed(() =>
  Boolean(
    filters.value.keyword.trim() ||
    filters.value.scope.trim() ||
    filters.value.leader.trim() ||
    filters.value.status,
  ),
)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / size.value)))

function zeroStats(): Stat[] {
  return statLabels.map((label) => ({ label, value: 0 }))
}

function setFeedback(message: string, isError: boolean) {
  feedback.value = message
  feedbackIsError.value = isError
}

function buildFilterParams(): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.value.keyword.trim()) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.scope.trim()) params.set('scope', filters.value.scope.trim())
  if (filters.value.leader.trim()) params.set('leader', filters.value.leader.trim())
  if (filters.value.status) params.set('status', filters.value.status)
  return params
}

function toCount(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0
}

/** 列表数据校验：字段不完整时抛出可读原因，而不是静默渲染残缺数据。 */
function parseListPayload(payload: unknown): { items: Row[]; total: number } {
  if (!payload || typeof payload !== 'object') {
    throw new Error('接口返回字段不完整：缺少列表数据体，请重试')
  }
  const data = payload as { items?: unknown; total?: unknown }
  if (!Array.isArray(data.items)) {
    throw new Error('接口返回字段不完整：缺少记录列表（items），请重试')
  }
  if (typeof data.total !== 'number' || !Number.isFinite(data.total) || data.total < 0) {
    throw new Error('接口返回字段不完整：缺少记录总数（total），请重试')
  }
  const items = data.items.filter(
    (item): item is Row => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
  )
  return { items, total: data.total }
}

/** 数量指标校验：指标缺失同样视为可重试的异常，避免卡片展示过期数字。 */
function parseStatsPayload(payload: unknown): Stat[] {
  if (!payload || typeof payload !== 'object') {
    throw new Error('接口返回字段不完整：缺少数量指标，请重试')
  }
  const data = payload as { total?: unknown; by_status?: unknown }
  if (!data.by_status || typeof data.by_status !== 'object' || Array.isArray(data.by_status)) {
    throw new Error('接口返回字段不完整：缺少数量指标，请重试')
  }
  const byStatus = data.by_status as Record<string, unknown>
  return [
    { label: '记录总数', value: toCount(data.total) },
    { label: '计划内审', value: toCount(byStatus['计划中']) },
    { label: '进行中内审', value: toCount(byStatus['执行中']) },
    { label: '待跟踪内审', value: toCount(byStatus['跟踪中']) },
  ]
}

async function reload() {
  loading.value = true
  loadError.value = ''
  // 重新加载期间先清空上一批记录与指标，避免短暂展示过期数据
  rows.value = []
  total.value = 0
  stats.value = zeroStats()
  const params = buildFilterParams()
  params.set('page', String(page.value))
  params.set('size', String(size.value))
  try {
    const [listPayload, statsPayload] = await Promise.all([
      fetchJson<unknown>(`${ENDPOINT}?${params.toString()}`),
      fetchJson<unknown>(`${ENDPOINT}/stats`),
    ])
    const parsed = parseListPayload(listPayload)
    const nextStats = parseStatsPayload(statsPayload)
    rows.value = parsed.items
    total.value = parsed.total
    stats.value = nextStats
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '内审记录列表读取失败，请重试'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', scope: '', leader: '', status: '' }
  page.value = 1
  void reload()
}

function goPage(target: number) {
  const next = Math.min(Math.max(target, 1), pageCount.value)
  if (next === page.value) return
  page.value = next
  void reload()
}

function changePageSize() {
  page.value = 1
  void reload()
}

function exportRows() {
  const query = buildFilterParams().toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  setFeedback('内审记录登记入口尚未接入审批流', true)
}

async function runAction(action: string, row: Row) {
  setFeedback('', false)
  const entryId = row.id
  if (entryId === null || entryId === undefined || entryId === '') {
    setFeedback('该记录缺少 id 字段，无法执行动作，请刷新列表后重试', true)
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    if (!response.ok) {
      throw new Error(extractErrorDetail(payload) || `接口返回 ${response.status}，动作未生效`)
    }
    if (!payload || typeof payload !== 'object' || typeof (payload as { ok?: unknown }).ok !== 'boolean') {
      throw new Error('接口返回字段不完整：缺少动作结果，请重试')
    }
    const result = payload as { ok: boolean; message?: string }
    if (!result.ok) {
      setFeedback(result.message || '动作未生效，请稍后重试', true)
      return
    }
    setFeedback(result.message || '动作已生效', false)
    await reload()
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : '内审管理操作失败', true)
  }
}

onMounted(reload)
</script>

<style scoped>
.empty-state p {
  margin: 4px 0 8px;
}
.pager {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.pager select,
.filter-item select,
.filter-item input {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  background: #fff;
}
.feedback-ok {
  color: #067647;
}
</style>
