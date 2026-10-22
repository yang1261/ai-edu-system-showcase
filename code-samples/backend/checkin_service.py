# 签到服务 — 课包匹配、课时计算、微信通知
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.student import Student, StudentAccount
from app.models.student_package import StudentPackage
from app.models.class_group import ClassGroup
from app.models.user import User
from app.models.campus import Campus
from app.models.course import Course
from app.models.parent_binding import ParentBinding
from app.models.wechat_log import WechatMessageLog
from app.services.wechat import WechatService

logger = logging.getLogger(__name__)


def find_matching_package(db: Session, student_id: int, class_group: ClassGroup) -> Optional[StudentPackage]:
    """为某学生+班级找到最合适的课包进行扣减（同班学生统一匹配逻辑）"""
    if not class_group:
        return None

    packages = db.query(StudentPackage).filter(
        StudentPackage.student_id == student_id,
    ).order_by(StudentPackage.id).all()
    if not packages:
        return None

    # 解析班级所属校区名，用于优先匹配同校区课包
    campus_name = ""
    if class_group.campus_id:
        campus = db.query(Campus).filter(Campus.id == class_group.campus_id).first()
        if campus:
            campus_name = campus.name

    course = (class_group.course_name or "").lower()
    subject = (class_group.subject_name or "").lower()

    def best_match(matches):
        if not matches:
            return None
        if campus_name:
            for pkg in matches:
                if (pkg.campus_name or "") == campus_name:
                    return pkg
        return matches[0]

    # 1. course_name/subject_name 含在 package_name 中
    candidates = []
    for pkg in packages:
        pkg_name = (pkg.package_name or "").lower()
        if (course and course in pkg_name) or (subject and subject in pkg_name):
            candidates.append(pkg)
    if candidates:
        return best_match(candidates)

    # 2. package_name 含在 course_name 中（反向匹配）
    candidates = []
    for pkg in packages:
        pkg_name = (pkg.package_name or "").lower()
        if course and pkg_name in course:
            candidates.append(pkg)
    if candidates:
        return best_match(candidates)

    # 3. 统一兜底：含"常规"的课包
    candidates = []
    for pkg in packages:
        pkg_name = (pkg.package_name or "").lower()
        if '常规' in pkg_name:
            candidates.append(pkg)
    if candidates:
        return best_match(candidates)

    # 4. 最后 fallback：取第一个课包
    return best_match(packages)


def get_course_hours(db: Session, class_group: ClassGroup) -> float:
    """根据班级获取标准课时数，优先级：班级设定 > 课程设定 > 默认2小时"""
    if class_group.student_hours and float(class_group.student_hours) > 0:
        return float(class_group.student_hours)
    course = db.query(Course).filter(Course.name == class_group.course_name).first()
    return float(course.hours) if course and course.hours else 2.0


def send_checkin_notification(
    db: Session,
    student_id: int,
    class_name: str,
    teacher_name: str,
    checkin_time: str,
    hours: float,
):
    """发送签到微信通知给家长（如有绑定），失败不影响签到流程"""
    binding = db.query(ParentBinding).filter(
        ParentBinding.student_id == student_id,
        ParentBinding.is_bound == True,
        ParentBinding.unsubscribe == False,
    ).first()
    if not binding:
        return

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return

    account = db.query(StudentAccount).filter(
        StudentAccount.student_id == student_id
    ).first()
    remain = 0
    if account:
        remain = float(account.total_hours or 0) - float(account.consumed_hours or 0)

    try:
        wechat = WechatService()
        result = wechat.send_checkin_notification(
            openid=binding.openid,
            student_name=student.name,
            course_name=class_name,
            class_time=checkin_time,
            teacher_name=teacher_name,
            remain_hours=max(0, remain),
        )
        log = WechatMessageLog(
            student_id=student_id,
            parent_binding_id=binding.id,
            openid=binding.openid,
            status="success" if result else "fail",
            error_msg="" if result else "发送失败",
        )
        db.add(log)
    except Exception as e:
        log = WechatMessageLog(
            student_id=student_id,
            parent_binding_id=binding.id,
            openid=binding.openid,
            status="fail",
            error_msg=str(e)[:500],
        )
        db.add(log)
    db.flush()
