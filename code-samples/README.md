# 代码样例说明

以下文件来自真实生产项目的**脱敏节选**，用于展示代码风格与关键设计。

## 阅读须知

- 文件中的 `app.config`、`app.models.*`、`app.auth.*` 等依赖模块未包含在本仓库中，因此**不能直接运行**
- 所有真实学员/家长信息、密钥、生产配置、品牌与校区标识均已移除或替换为示例值
- 代码注释保留原样，便于理解设计意图

## 推荐阅读顺序

### 后端

1. **`knowledge_service.py`** — 从文档到可检索知识库的完整链路：语义切分 → 本地向量化 → FAISS 索引 → 相似度检索
2. **`ai_service_schema.py`** — 业务表 Schema 注册：把数据库结构翻译成 LLM 能理解的业务语言
3. **`ai_chat.py`** — AI 助手路由：System Prompt 组装、角色/校区行级隔离、只读 SQL 校验、SSE 流式输出
4. **`ai_service.py`** — 双模型 Provider 封装：统一接口、流式输出、Function Calling、token 用量统计
5. **`checkin_service.py`** — 业务复杂度示例：课包四级匹配策略、课时解析优先级、通知降级

### 前端

1. **`useMobile.ts`** — 移动端能力封装：路由判定、Tabbar 权限过滤、详情页/登录页隐藏规则
2. **`MobileLayout.vue`** — Vant 移动端骨架：动态导航栏 + 底部标签栏
3. **`mobileTabbar.ts`** — 导航配置（角色维度可扩展）
4. **`home.vue`** — 家长端首页：多孩切换、课包到期提醒、剩余学费展示
5. **`mobile-student-index.vue`** — 移动端学生管理：表格 → 票卡式布局
