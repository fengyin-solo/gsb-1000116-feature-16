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
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ loading ? '…' : hasError ? '—' : item.value }}</strong>
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
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">内审记录加载中…</td>
        </tr>
        <tr v-else-if="hasError">
          <td :colspan="columns.length + 1" class="empty-state state-error">
            <p class="state-title">内审记录加载失败：{{ errorMessage }}</p>
            <p class="state-hint">当前未展示任何记录，请确认后端服务可用后重试。</p>
            <button class="btn primary" type="button" @click="reload()">重新加载</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <p class="state-title">{{ emptyTitle }}</p>
            <p class="state-hint">{{ emptyHint }}</p>
          </td>
        </tr>
        <template v-else>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">
              <span v-if="row[column] ?? ''">{{ row[column] }}</span>
              <span v-else class="cell-missing" :title="missingTitle(row, column)">字段缺失</span>
            </td>
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
          <tr v-if="incompleteCount">
            <td :colspan="columns.length + 1" class="incomplete-note">
              有 {{ incompleteCount }} 条内审记录字段不完整（缺少：内审编号、审核范围、审核组长或内审状态），请补录后再流转
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <footer class="page-foot">
      <span v-if="!hasError">共 {{ total }} 条内审管理记录</span>
      <span v-else class="error-text">记录数量暂不可用，重试成功后会与列表同步更新</span>
      <span v-if="noticeMessage" class="error-text notice-text">{{ noticeMessage }}</span>
      <div class="pager" v-if="!hasError">
        <label class="page-size">
          每页
          <select v-model.number="size" @change="changePageSize">
            <option v-for="option in sizeOptions" :key="option" :value="option">{{ option }}</option>
          </select>
          条
        </label>
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="gotoPage(page - 1)">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ totalPages }} 页</span>
        <button class="btn" type="button" :disabled="page >= totalPages || loading" @click="gotoPage(page + 1)">下一页</button>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | string[] | null>

interface ListPayload {
  items: unknown
  total: unknown
  summary?: unknown
  page?: unknown
  size?: unknown
}

const ENDPOINT = '/api/audit'
const columns = ['内审编号', '审核范围', '审核组长', '审核日期', '不符合项', '纠正期限', '跟踪验证', '内审状态']
const actions = ['开始内审', '完成内审', '跟踪验证']
const statuses = ['计划中', '执行中', '已完成', '跟踪中']
const sizeOptions = [1, 10, 20, 50, 100, 200]
const summaryLabels = ['计划内审', '进行中内审', '待跟踪内审']

const rows = ref<Row[]>([])
const total = ref(0)
const summary = ref<Record<string, number>>({})
const page = ref(1)
const size = ref(20)
const loading = ref(false)
const hasError = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<{ keyword: string; scope: string; leader: string; status: string }>({
  keyword: '',
  scope: '',
  leader: '',
  status: '',
})
let requestSeq = 0

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const statCards = computed(() =>
  summaryLabels.map((label) => ({ label, value: summary.value[label] ?? 0 })),
)
const incompleteCount = computed(
  () => rows.value.filter((row) => row.incomplete === true).length,
)
const emptyTitle = computed(() =>
  hasActiveFilters.value ? '没有符合条件的内审记录' : '暂无内审记录',
)
const emptyHint = computed(() =>
  hasActiveFilters.value
    ? '当前筛选条件（内审编号、审核范围、审核组长或内审状态）下结果为空，可调整条件或重置后重试'
    : '系统中还没有任何内审记录，可先登记内审记录',
)
const hasActiveFilters = computed(() =>
  Object.values(filters.value).some((value) => value.trim() !== ''),
)

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', scope: '', leader: '', status: '' }
  page.value = 1
  void reload()
}

function gotoPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) return
  page.value = target
  void reload()
}

function changePageSize() {
  page.value = 1
  void reload()
}

function buildQuery() {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) params.set(key, value.trim())
  }
  params.set('page', String(page.value))
  params.set('size', String(size.value))
  return params.toString()
}

function exportRows() {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) params.set(key, value.trim())
  }
  window.open(`${ENDPOINT}/export?${params.toString()}`, '_blank')
}

function openCreate() {
  noticeMessage.value = '内审记录登记入口尚未接入审批流，暂时无法登记'
}

function missingTitle(row: Row, column: string): string {
  const missing = Array.isArray(row.missing_fields) ? (row.missing_fields as string[]) : []
  return missing.includes(column) ? `该记录缺少必填字段：${column}` : '该记录暂无此字段内容'
}

async function readErrorDetail(response: Response, fallback: string) {
  try {
    const data: unknown = await response.json()
    if (data && typeof data === 'object' && 'detail' in data) {
      const detail = (data as { detail: unknown }).detail
      if (typeof detail === 'string' && detail) return detail
    }
  } catch {
    // 错误响应不是 JSON 时退回通用说明
  }
  return `${fallback}（HTTP ${response.status}）`
}

/** 校验响应结构：字段不完整 / 形态不对时直接判定为异常，避免半成品数据上屏。 */
function normalizePayload(payload: unknown): { items: Row[]; total: number; summary: Record<string, number> } {
  if (!payload || typeof payload !== 'object') {
    throw new Error('接口返回内容为空或格式不正确，请重试')
  }
  const data = payload as ListPayload
  if (!Array.isArray(data.items)) {
    throw new Error('接口未返回内审记录列表（items 缺失），请重试')
  }
  if (typeof data.total !== 'number' || !Number.isFinite(data.total)) {
    throw new Error('接口未返回有效的记录总数（total 缺失），请重试')
  }
  const items: Row[] = []
  for (const [index, raw] of data.items.entries()) {
    if (!raw || typeof raw !== 'object') {
      throw new Error(`第 ${index + 1} 条内审记录结构不完整，请重试`)
    }
    items.push(raw as Row)
  }
  let nextSummary: Record<string, number> = {}
  if (data.summary && typeof data.summary === 'object') {
    nextSummary = Object.fromEntries(
      Object.entries(data.summary as Record<string, unknown>).filter(
        (entry): entry is [string, number] => typeof entry[1] === 'number',
      ),
    )
  }
  return { items, total: data.total, summary: nextSummary }
}

async function reload() {
  const seq = ++requestSeq
  loading.value = true
  noticeMessage.value = ''
  // 先清空上一批记录：加载期间绝不暂时展示旧数据
  rows.value = []
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, '内审记录列表读取失败'))
    }
    const { items, total: nextTotal, summary: nextSummary } = normalizePayload(await response.json())
    // 只接受最后一次请求的结果，避免重试 / 快速翻页时旧响应覆盖新数据
    if (seq !== requestSeq) return
    // 记录、数量指标、状态汇总来自同一次响应，一次性原子提交
    rows.value = items
    total.value = nextTotal
    summary.value = nextSummary
    hasError.value = false
    if (page.value > totalPages.value) {
      page.value = totalPages.value
    }
  } catch (error) {
    if (seq !== requestSeq) return
    // 失败时保持空列表并同步清零数量指标，避免指标与列表口径不一致
    rows.value = []
    total.value = 0
    summary.value = {}
    hasError.value = true
    errorMessage.value = error instanceof Error ? error.message : '内审管理列表读取失败'
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

async function runAction(action: string, row: Row) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, '内审管理动作未生效，请稍后重试'))
    }
    const data: unknown = await response.json()
    if (data && typeof data === 'object' && (data as { ok?: unknown }).ok === false) {
      throw new Error(String((data as { message?: unknown }).message ?? '内审管理动作未生效，请稍后重试'))
    }
    // 动作成功后重新拉取，记录与状态、数量指标一起刷新
    await reload()
  } catch (error) {
    // 动作失败不替换列表，仅在页脚说明原因
    noticeMessage.value = error instanceof Error ? error.message : '内审管理操作失败'
  }
}

onMounted(reload)
</script>
