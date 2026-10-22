<template>
  <div class="edu-mobile-app">
    <!-- 顶部导航栏：仅子页面显示，首页不显示 -->
    <van-nav-bar
      v-if="showNavBar"
      :title="pageTitle"
      left-arrow
      @click-left="handleBack"
      fixed
      placeholder
      safe-area-inset-top
    />

    <!-- 主内容区 -->
    <div class="mobile-content" :class="{ 'has-navbar': showNavBar, 'has-tabbar': showTabbar }">
      <router-view v-slot="{ Component }">
        <transition name="m-page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>

    <!-- 底部标签栏 -->
    <van-tabbar
      v-if="showTabbar"
      v-model="activeTab"
      :fixed="true"
      :border="true"
      :safe-area-inset-bottom="true"
      active-color="#c4956a"
      inactive-color="#8b7e5c"
      @change="onTabChange"
    >
      <van-tabbar-item
        v-for="item in tabbarItems"
        :key="item.name"
        :name="item.name"
        :icon="item.icon"
      >
        {{ item.label }}
      </van-tabbar-item>
    </van-tabbar>

    <!-- "更多"溢出菜单 -->
    <van-action-sheet
      v-model:show="showMoreSheet"
      title="更多功能"
      :actions="moreActionsForSheet"
      cancel-text="取消"
      close-on-click-action
      @select="onMoreSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useMobile } from '@/composables/useMobile'

const route = useRoute()
const router = useRouter()
// 刷新后从 localStorage 恢复用户信息与 allowedKeys（Tabbar 权限过滤依赖）
const userStore = useUserStore()
userStore.loadUser()
const { tabbarItems, moreItems, currentPageKey, showTabbar } = useMobile()

const showMoreSheet = ref(false)

const showNavBar = computed(() => {
  // 首页不显示 navbar
  if (route.path === '/m/dashboard' || route.path === '/m') return false
  return route.meta.showNavBar !== false && !!route.meta.title
})

const pageTitle = computed(() => (route.meta.title as string) || '')

const activeTab = computed({
  get: () => currentPageKey.value,
  set: () => { /* handled in onTabChange */ },
})

/** 更多菜单项转换为 Vant ActionSheet 格式 */
const moreActionsForSheet = computed(() =>
  moreItems.value.map(item => ({
    name: item.label,
    subname: '',
    ...item,
  }))
)

function onTabChange(name: string | number) {
  if (name === 'more') {
    showMoreSheet.value = true
    return
  }
  // 查找对应 tab 的路径并导航
  const item = tabbarItems.value.find(t => t.name === name)
  if (item && item.path) {
    router.push(item.path)
  }
}

function onMoreSelect(action: any) {
  if (action.path) {
    router.push(action.path)
  }
}

function handleBack() {
  if (window.history.length > 1) router.back()
  else router.push('/m/dashboard')
}
</script>
