"""
数据库 Schema 自动生成器

扫描 SQLAlchemy 模型定义，生成供 LLM 理解的 Schema 描述。
直接从 Base.metadata.tables 读取，不需要数据库连接。
"""

from app.database import Base


# ── 业务说明（给 LLM 理解每个表的用途） ──
TABLE_BUSINESS_DESCRIPTIONS = {
    "student": "学员基本信息表。每个学生一条记录，包含姓名、年级、家长电话、报名日期、在读课程等。status: 在读/停课/毕业/流失",
    "student_account": "学员课时账户聚合表。每个学生一条记录（与 student 一对一），汇总 total_paid(累计实缴)、consumed_hours(已消耗课时) 等",
    "student_phone": "学员联系电话表。一个学生可能有多个联系电话（父亲/母亲）",
    "class_group": "班级信息表。包含班级名称、授课教师、课程名称、上课时间段、教室、开班日期、状态等",
    "class_enrollment": "学员报班关联表。记录学生属于哪个班级",
    "class_record": "上课记录表（68k+条）。每节课一条记录，包含上课班级、学生、教师、课程类别、课时数、课消金额、到课状态(到课/请假/旷课)等",
    "course": "课程信息表（80+门课）。包含课程名称、分类(低龄/机器人/编程/信奥/算法思维/赛考)、级别、适龄范围等",
    "course_progression": "课程进阶映射表。记录课程之间的进阶关系（学完A可以学B）",
    "checkin_record": "签到记录表。记录每次签到操作，包含班级、学生、教师、签到日期、状态(正常/迟到/请假)等",
    "checkin_supplement": "签到补录表。用于临时添加学生到某天的签到列表",
    "schedule": "排课计划表。记录具体的排课实例（上课日期时间），由排课规则自动生成或手动添加",
    "schedule_rule": "排课规则表。定义周期性上课规则（周几、起止日期、上课模式），用于批量生成排课计划",
    "campus": "校区信息表。多校区管理，包含校区名称",
    "sys_user": "系统用户表。管理员/教师/教务等账号，包含角色、校区、分组、状态等",
    "role": "角色权限表。定义角色及其权限编码列表",
    "user_group": "用户分组表。用于教师分组管理，组长可管理组内成员的数据",
    "student_package": "学员课包表。每个学生可拥有多个课包，每个课包包含总课时、已消耗、剩余课时、金额信息",
    "tuition_record": "缴费记录表。记录每次缴费的金额、课时、支付方式等",
    "assessment_record": "学员测评记录表。记录学员的阶段性测评成绩和评语",
    "competition_award": "学员竞赛获奖记录表。记录学员参赛获奖信息",
    "parent_binding": "家长微信绑定表。记录家长微信与学员的绑定关系",
    "wechat_message_log": "微信消息日志表。记录微信模板消息的发送历史",
    "payment_order": "在线支付订单表。记录微信支付订单信息",
    "transfer_record": "转课包记录表。记录将一个课包余额转到另一个课包的操作",
    "renewal_record": "续费记录表。记录课包续费的快照信息",
    "refund_record": "退费记录表。记录退费操作及快照",
    "teacher_center_pay": "中心课酬统计表",
    "external_class_detail": "外课明细表",
    "trial_class_detail": "试听课明细表",
    "part_time_class_detail": "兼职明细表",
    "refund_detail": "退费明细表",
    "student_flow_record": "学生流转记录表",
}


def _get_column_description(col) -> str:
    """从列注释和名称推断业务含义"""
    comment = col.comment or ""
    name_hints = {
        "id": "唯一ID",
        "name": "名称",
        "phone": "联系电话",
        "status": "状态",
        "campus_id": "所属校区ID",
        "student_id": "学员ID（外键 → student.id）",
        "class_id": "班级ID（外键 → class_group.id）",
        "teacher_id": "教师用户ID（外键 → sys_user.id）",
        "course_id": "课程ID（外键 → course.id）",
        "create_time": "创建时间",
        "update_time": "更新时间",
        "is_deleted": "删除标记(0=正常, 1=已删除)",
    }
    hint = name_hints.get(col.name, "")
    if comment:
        return comment
    return hint


def generate_schema_prompt(include_sample_queries: bool = True) -> str:
    """
    生成供 LLM 使用的 Schema 提示文本。
    包含表结构、字段、外键关系、示例查询。
    """
    lines = [
        "你是一个数据库查询助手。下面是教务系统的完整数据库 Schema，请基于此生成 SQL 查询来回答用户问题。\n",
        "规则：",
        "1. 只能生成 SELECT 查询，绝不允许 INSERT/UPDATE/DELETE/DROP",
        "2. 表名可能和业务概念不完全一致，注意查看字段说明",
        "3. 多表关联时注意外键关系",
        "4. 日期字段格式为 YYYY-MM-DD，日期函数使用 PostgreSQL 语法（如 CURRENT_DATE, INTERVAL '7 days'）",
        "5. 状态字段使用中文值（如 status='在读'）",
        "6. 字符串使用单引号（PostgreSQL 标准）",
        "7. 金额单位为元，课时单位为小时",
        "8. 查询结果限制最多 100 条",
        "9. 数据库类型: PostgreSQL",
        "",
        "=== 数据库 Schema ===",
    ]

    # 按业务领域分组排列表格
    table_groups = {
        "👤 学员管理": ["student", "student_account", "student_phone", "student_flow_record"],
        "📚 班级与课程": ["class_group", "class_enrollment", "class_record", "course", "course_progression"],
        "✅ 签到与排课": ["checkin_record", "checkin_supplement", "schedule", "schedule_rule"],
        "🏫 校区与用户": ["campus", "sys_user", "role", "user_group"],
        "💰 财务与课包": ["student_package", "tuition_record", "payment_order", "transfer_record", "renewal_record", "refund_record"],
        "📊 测评与竞赛": ["assessment_record", "competition_award"],
        "📱 微信集成": ["parent_binding", "wechat_message_log"],
        "💼 薪酬统计": ["teacher_center_pay", "external_class_detail", "trial_class_detail", "part_time_class_detail", "refund_detail"],
    }

    for group_name, table_names in table_groups.items():
        lines.append(f"\n## {group_name}")
        for table_name in table_names:
            if table_name not in Base.metadata.tables:
                continue
            table = Base.metadata.tables[table_name]
            biz_desc = TABLE_BUSINESS_DESCRIPTIONS.get(table_name, "")
            lines.append(f"\n### 表: {table_name}")
            if biz_desc:
                lines.append(f"  说明: {biz_desc}")

            for col in table.columns:
                pk = "🔑" if col.primary_key else "  "
                nullable = "NULL" if col.nullable else "NOT NULL"
                col_desc = _get_column_description(col)
                default = f" DEFAULT {col.default.arg}" if col.default and hasattr(col.default, 'arg') else ""
                type_str = str(col.type)
                # 简化类型名
                type_str = type_str.replace("VARCHAR", "文本").replace("INTEGER", "整数").replace("NUMERIC", "数值").replace("DATE", "日期").replace("DATETIME", "日期时间").replace("TEXT", "长文本")
                lines.append(f"  {pk} {col.name} ({type_str}) {nullable}{default}  — {col_desc}")

            # 外键
            for fk in col.foreign_keys:
                lines.append(f"     ↳ 外键: {fk.column.table.name}.{fk.column.name}")

    if include_sample_queries:
        lines.extend([
            "",
            "=== 常用查询示例 ===",
            "",
            "-- 查询某个学生的所有课包信息",
            "SELECT s.name, sp.course_package_type, sp.total_hours, sp.consumed_hours, sp.remain_hours, sp.total_fee ",
            "FROM student s JOIN student_package sp ON s.id = sp.student_id WHERE s.name = '张三';",
            "",
            "-- 查询最近7天的签到记录",
            "SELECT s.name, c.checkin_date, c.status FROM checkin_record c JOIN student s ON c.student_id = s.id WHERE c.checkin_date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY c.checkin_date DESC;",
            "",
            "-- 统计各校区在读学生数",
            "SELECT cp.name, COUNT(*) as 在读人数 FROM student s JOIN campus cp ON s.campus_id = cp.id WHERE s.status = '在读' GROUP BY cp.name;",
            "",
            "-- 查询课时不足预警的学生",
            "SELECT s.name, s.phone, sp.remain_hours FROM student s JOIN student_package sp ON s.id = sp.student_id WHERE s.status = '在读' AND sp.remain_hours < 5 ORDER BY sp.remain_hours;",
        ])

    return "\n".join(lines)


def get_table_column_info() -> list[dict]:
    """获取机器可读的 Schema 信息（供前端调试用）"""
    result = []
    for table_name, table in Base.metadata.tables.items():
        cols = []
        for col in table.columns:
            cols.append({
                "name": col.name,
                "type": str(col.type),
                "primary_key": col.primary_key,
                "nullable": col.nullable,
                "description": _get_column_description(col),
                "foreign_keys": [
                    {"table": fk.column.table.name, "column": fk.column.name}
                    for fk in col.foreign_keys
                ],
            })
        result.append({
            "table": table_name,
            "description": TABLE_BUSINESS_DESCRIPTIONS.get(table_name, ""),
            "columns": cols,
        })
    return result
