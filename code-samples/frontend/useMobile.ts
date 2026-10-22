import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { getTabbarConfig, getMoreActions } from '@/config/mobileTabbar'

export function useMobile() {
  const route = useRoute()
  const userStore = useUserStore()

  /** 当前是否在移动端路由 */
  const isMobileRoute = computed(() => route.path.startsWith('/m'))

  /** 当前用户角色 */
  const roleCode = computed(() => userStore.userInfo?.role_code || 'teacher')

  /** Tabbar 配置项（按 allowedKeys 过滤；首页/我的始终可见） */
  const tabbarItems = computed(() => {
    const items = getTabbarConfig(roleCode.value)
    if (userStore.userInfo?.role_code === 'super_admin') return items
    // 与路由守卫语义一致：本地无已存权限数据时不过滤（登录流程会写入）
    if (!localStorage.getItem('allowedKeys')) return items
    return items.filter(
      i => i.name === 'dashboard' || i.name === 'profile' || userStore.canAccessKey(i.name)
    )
  })

  /** "更多"菜单项 */
  const moreItems = computed(() => getMoreActions(roleCode.value))

  /** 当前页面路由 key（如 'students'） */
  const currentPageKey = computed(() => {
    return route.path.replace('/m/', '').split('/')[0]
  })

  /** 是否为登录页 */
  const isLoginRoute = computed(() => route.path === '/m/login')

  /** 是否为详情页（路径含数字 ID 参数） */
  const isDetailRoute = computed(() => {
    const segments = route.path.split('/')
    // 路径段中包含纯数字的视为详情页，如 /m/students/123
    return segments.some(s => /^\d+$/.test(s))
  })

  /** 是否显示底部 Tabbar（仅列表/首页，登录页和详情页隐藏） */
  const showTabbar = computed(() => {
    if (!isMobileRoute.value) return false
    if (isLoginRoute.value) return false
    if (isDetailRoute.value) return false
    // 异常页、AI 页、通知页也不显示 tabbar
    if (route.path === '/m/checkin-exceptions') return false
    return true
  })

  /** 回退导航 */
  function goBack(fallback = '/m/dashboard') {
    if (window.history.length > 1) {
      window.history.back()
    } else {
      window.location.hash = '#' + fallback
    }
  }

  return {
    isMobileRoute,
    roleCode,
    tabbarItems,
    moreItems,
    currentPageKey,
    isLoginRoute,
    isDetailRoute,
    showTabbar,
    goBack,
  }
}
