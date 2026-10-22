<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getMyChildren, type ChildOverview } from '@/api/parent'
import Astronaut from './Astronaut.vue'

const router = useRouter()
const children = ref<ChildOverview[]>([])
const loading = ref(true)
const error = ref('')

// 学生状态 → 宇宙色标签
const studentTag: Record<string, { bg: string; text: string }> = {
  在读: { bg: 'rgba(143,201,242,0.26)', text: '#2A5B86' },
  停课: { bg: 'rgba(255,217,138,0.38)', text: '#8A6A18' },
  毕业: { bg: 'rgba(179,166,240,0.28)', text: '#5B4F9E' },
  流失: { bg: 'rgba(108,119,166,0.18)', text: '#5A6390' },
  退费: { bg: 'rgba(108,119,166,0.18)', text: '#5A6390' },
}
function tag(s: string) {
  return studentTag[s] || { bg: 'rgba(108,119,166,0.18)', text: '#5A6390' }
}

// 课包到期临近（15 天内）
function expiringSoon(date: string | null): boolean {
  if (!date) return false
  const d = new Date(date + 'T00:00:00')
  const now = new Date()
  const days = (d.getTime() - now.getTime()) / 86400000
  return days >= 0 && days <= 15
}

// 剩余学费：保留到分（两位小数），千分位
function money(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getMyChildren()
    children.value = res.children
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败，请下拉重试'
  } finally {
    loading.value = false
  }
}

function openRecords(c: ChildOverview) {
  router.push(`/parent/child/${c.student_id}`)
}
function logout() {
  localStorage.removeItem('parent_token')
  localStorage.removeItem('parent_phone')
  router.replace('/parent/login')
}

onMounted(load)
</script>

<template>
  <div class="sky-app min-h-screen">
    <header class="sticky top-0 z-20 sky-glass px-5 h-14 flex items-center justify-between rounded-b-[22px]">
      <div class="flex items-baseline gap-2">
        <span class="sky-display text-lg">我的孩子</span>
        <span v-if="children.length" class="text-xs text-[var(--navy-soft)]">{{ children.length }} 位</span>
      </div>
      <button class="sky-focus text-sm text-[var(--navy-soft)] active:text-[var(--orange)] rounded-lg px-2 py-1" @click="logout">退出</button>
    </header>

    <div class="px-4 pt-4 pb-8 space-y-4 max-w-md mx-auto">
      <!-- 问候 + 吉祥物 -->
      <div class="flex items-center gap-3 px-1 sky-rise">
        <div class="sky-float shrink-0"><Astronaut :size="60" /></div>
        <div>
          <p class="sky-display text-[17px]">你好呀，家长 👋</p>
          <p class="text-xs text-[var(--navy-soft)] mt-0.5">这是孩子的 AI 星球，实时同步课时</p>
        </div>
      </div>

      <p v-if="loading" class="text-center text-[var(--navy-soft)] py-16">正在连接星球…</p>
      <div v-else-if="error" class="text-center py-16">
        <p class="text-[#E24E3A] text-sm">{{ error }}</p>
        <button class="mt-3 text-sm text-[var(--orange)] underline" @click="load">重新加载</button>
      </div>
      <p v-else-if="!children.length" class="text-center text-[var(--navy-soft)] py-16">还没有查询到孩子信息 ✦</p>

      <!-- 学习星球卡 -->
      <article
        v-for="(c, i) in children"
        :key="c.student_id"
        class="sky-glass rounded-[30px] p-5 sky-rise"
        :style="{ animationDelay: 60 + i * 70 + 'ms' }"
      >
        <!-- 头部：姓名 + 状态 + 最近上课 -->
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="sky-display text-xl truncate">{{ c.name }}</span>
            <span class="shrink-0 text-xs px-2.5 py-0.5 rounded-full font-medium" :style="{ background: tag(c.status).bg, color: tag(c.status).text }">{{ c.status }}</span>
          </div>
          <span class="shrink-0 text-xs text-[var(--navy-soft)]">最近上课 {{ c.last_class_date || '—' }}</span>
        </div>

        <!-- 校区 · 班级 -->
        <div class="mt-2 flex items-center gap-1.5 text-xs text-[var(--navy-soft)]">
          <span>{{ c.campus_name || '—' }}</span>
          <span class="text-[#C6CEE6]">·</span>
          <span class="truncate">{{ c.class_name || '—' }}</span>
        </div>

        <!-- 星球 + 剩余课时 -->
        <div class="mt-4 flex items-center gap-5">
          <div class="relative w-[92px] h-[92px] shrink-0" aria-hidden="true">
            <div class="sky-spin absolute inset-0">
              <div class="sky-orbit absolute inset-0"></div>
              <div class="absolute left-1/2 -top-[3px] -translate-x-1/2 w-3 h-3 rounded-full" style="background: radial-gradient(circle at 35% 30%, #fff 0%, #FFD98A 55%, #F5B94A 100%); box-shadow: 0 0 6px rgba(245,185,74,.7)"></div>
            </div>
            <div class="absolute inset-[15px]" :class="c.low_hours ? 'sky-planet--low' : 'sky-planet'"></div>
          </div>

          <div class="min-w-0">
            <div class="flex items-baseline gap-1.5">
              <span class="sky-num text-[3.4rem] leading-none" :class="{ 'sky-num--low': c.low_hours }">{{ c.remaining_hours }}</span>
              <span class="text-sm text-[var(--navy-soft)] mb-1">课时剩余</span>
            </div>
            <div v-if="c.low_hours" class="mt-2 inline-flex items-center gap-1.5 text-[13px] text-[#E24E3A] bg-[#FF6A4D]/10 rounded-full px-3 py-1">
              <span class="w-1.5 h-1.5 rounded-full bg-[#E24E3A]"></span>课时快用完啦，记得补给 🚀
            </div>
          </div>
        </div>

        <!-- 补给舱：课包明细 -->
        <div v-if="c.packages.length" class="mt-5 pt-4 border-t border-dashed border-[#D7DEF2]">
          <div class="text-xs text-[var(--navy-soft)] mb-1 flex items-center gap-1">✦ 补给舱 · 课包</div>
          <div
            v-for="(p, pi) in c.packages"
            :key="pi"
            class="flex items-center justify-between gap-3 py-2.5 border-b border-[#EAEEFA] last:border-0"
          >
            <div class="min-w-0">
              <div class="text-sm text-[var(--navy)] truncate">{{ p.name }}</div>
              <div class="text-xs text-[var(--navy-soft)] mt-0.5">
                <span :class="{ 'text-[#8A6A18]': p.status === '停课' }">{{ p.status }}</span>
                <span v-if="p.teach_mode"> · {{ p.teach_mode }}</span>
                <span v-if="p.expire_date">
                  · <span :class="{ 'text-[#E24E3A]': expiringSoon(p.expire_date) }">到期 {{ p.expire_date }}{{ expiringSoon(p.expire_date) ? '（临近）' : '' }}</span>
                </span>
              </div>
            </div>
            <div class="shrink-0 text-right">
              <div>
                <span class="sky-display text-lg" :class="p.remaining_hours > 0 ? 'text-[var(--navy)]' : 'text-[#B4BCD8]'">{{ p.remaining_hours }}</span>
                <span class="text-xs text-[var(--navy-soft)]"> 课时</span>
              </div>
              <div class="text-xs text-[var(--navy-soft)] mt-0.5">剩 ¥{{ money(p.remaining_tuition) }}</div>
            </div>
          </div>
        </div>
        <p v-else class="mt-4 text-sm text-[var(--navy-soft)]">暂无在读课包</p>

        <button
          class="sky-btn sky-focus w-full h-12 rounded-2xl mt-5 text-sm font-semibold flex items-center justify-center gap-1"
          @click="openRecords(c)"
        >查看航行日志 <span aria-hidden="true">›</span></button>
      </article>
    </div>
  </div>
</template>
