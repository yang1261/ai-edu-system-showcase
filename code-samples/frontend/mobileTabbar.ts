export interface TabbarItem {
  name: string
  label: string
  icon: string
  path: string
}

export interface MobileAction {
  key: string
  label: string
  path: string
}

// 所有角色统一 Tabbar：首页 | 学生 | 签到 | 记录 | 我的
const TABBAR: TabbarItem[] = [
  { name: 'dashboard', label: '首页', icon: 'home-o',    path: '/m/dashboard' },
  { name: 'students',  label: '学生', icon: 'friends-o', path: '/m/students' },
  { name: 'checkin',   label: '签到', icon: 'certificate', path: '/m/checkin' },
  { name: 'records',   label: '记录', icon: 'notes-o',   path: '/m/records' },
  { name: 'profile',   label: '我的', icon: 'user-o',    path: '/m/profile' },
]

export function getTabbarConfig(_roleCode?: string): TabbarItem[] {
  return TABBAR
}

export function getMoreActions(_roleCode?: string): MobileAction[] {
  return [] // 不再需要"更多"菜单
}
