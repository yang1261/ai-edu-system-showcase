<template>
  <div class="m-page">
    <van-search v-model="kw" placeholder="搜索学生姓名或手机号" shape="round" @search="load(true)" @clear="load(true)" />

    <!-- 校区 / 课包筛选 -->
    <div style="padding:0 16px 8px">
      <van-dropdown-menu active-color="#c4956a">
        <van-dropdown-item v-model="filterCampus" :options="campusOptions" @change="load(true)" />
        <van-dropdown-item v-model="filterPackage" :options="packageOptions" @change="load(true)" />
      </van-dropdown-menu>
    </div>

    <div class="m-filter-row">
      <span v-for="s in statusOpts" :key="s.value" class="m-filter-chip" :class="filterStatus===s.value&&'m-filter-chip--active'"
        @click="filterStatus=filterStatus===s.value?'':s.value;load(true)">{{ s.label }}</span>
    </div>
    <van-pull-refresh v-model="refr" @refresh="onR">
      <van-list v-model:loading="ld" :finished="fin" finished-text="— 已加载全部 —" @load="loadMore" :immediate-check="false">
        <div v-for="item in students" :key="item.id" class="m-scard" :data-status="item.status" @click="goDetail(item.id)">
          <div class="m-scard__head">
            <div class="m-scard__avatar">{{ item.name?.[0]||'?' }}</div>
            <div class="flex-1" style="min-width:0">
              <div class="m-scard__name">{{ item.name }}</div>
              <div class="m-scard__phone">{{ item.parent_phone||'—' }}</div>
            </div>
            <span class="m-ledger-num m-hero-num m-ledger-num--accent">
              {{ fmtH(item.remaining_hours) }}
              <label>剩余课时</label>
            </span>
          </div>
          <!-- 课时/学费小台账：票格组 -->
          <div class="m-scard__ledger">
            <div class="m-ledger-group">
              <span class="m-ledger-num">{{ fmtH(item.total_hours) }}<label>总课时</label></span>
              <span class="m-ledger-num">{{ fmtH(item.consumed_hours) }}<label>已用课时</label></span>
              <span class="m-ledger-num m-ledger-num--accent">{{ fmtH(item.remaining_hours) }}<label>剩余课时</label></span>
            </div>
            <div class="m-ledger-group">
              <span class="m-ledger-num">{{ fmtM(item.total_fee) }}<label>总学费</label></span>
              <span class="m-ledger-num">{{ fmtM(item.total_paid) }}<label>实缴</label></span>
              <span class="m-ledger-num">{{ fmtM(item.consumed_amount) }}<label>已用学费</label></span>
              <span class="m-ledger-num m-ledger-num--accent">{{ fmtM(item.remaining_tuition) }}<label>剩余学费</label></span>
              <span class="m-ledger-num" :class="item.debt_amount>0?'m-ledger-num--debt':''">{{ fmtM(item.debt_amount) }}<label>欠费</label></span>
            </div>
          </div>
          <div class="m-scard__body">
            <span class="m-badge" :class="badgeClass(item.status)">{{ item.status }}</span>
            <span class="m-scard__info" v-if="item.campus_name">{{ item.campus_name }}</span>
            <span class="m-scard__info" style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">· {{ classLabel(item) }}</span>
          </div>
        </div>
        <div v-if="!ld && students.length===0" class="m-empty">未找到学生，换个筛选条件试试</div>
      </van-list>
    </van-pull-refresh>

    <!-- FAB 新增学生 -->
    <div class="m-fab"><van-button type="primary" @click="openAdd"><van-icon name="plus" size="22"/></van-button></div>

    <!-- 新增学生表单 -->
    <van-action-sheet v-model:show="showAdd" title="新增学生" :round="true" :safe-area-inset-bottom="true">
      <div style="padding:0 16px 20px;max-height:70vh;overflow-y:auto">
        <van-form @submit="saveAdd">
          <van-field v-model="af.name" label="姓名" placeholder="必填" :rules="[{required:true,message:'请输入姓名'}]" />
          <van-field v-model="af.parent_phone" label="家长电话" type="tel" maxlength="11" placeholder="必填" :rules="[{required:true,message:'请输入家长电话'}]" />
          <van-field v-model="afCampusLabel" label="校区" is-link readonly placeholder="请选择校区" @click="showCampusPicker=true" :rules="[{required:true,message:'请选择校区'}]" />
          <van-field label="性别">
            <template #input>
              <div style="display:flex;gap:6px">
                <span v-for="g in ['男','女']" :key="g" class="m-filter-chip" :class="{'m-filter-chip--active':af.gender===g}" @click="af.gender=af.gender===g?'':g">{{ g }}</span>
              </div>
            </template>
          </van-field>
          <van-field v-model="af.grade" label="年级" placeholder="如：一年级" />
          <van-field v-model="af.school" label="学校" />
          <van-field v-model="af.parent_name" label="家长姓名" />
          <van-field v-model="af.notes" label="备注" />
          <div style="margin:16px 16px 4px"><van-button round block type="primary" native-type="submit" :loading="saving">保存（报名日期默认今天）</van-button></div>
        </van-form>
      </div>
    </van-action-sheet>

    <van-popup v-model:show="showCampusPicker" position="bottom" round>
      <van-picker :columns="campusPickerCols" title="选择校区" @confirm="onCampusConfirm" @cancel="showCampusPicker=false" />
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { getStudents, createStudent } from '@/api/student'
import { getCampuses } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { PACKAGE_TYPES } from '@/config/constants'

const router=useRouter()
const userStore=useUserStore()
const students=ref<any[]>([]),kw=ref(''),filterStatus=ref(''),refr=ref(false),ld=ref(false),fin=ref(false),page=ref(1)
const filterCampus=ref(0),filterPackage=ref('')
const campuses=ref<any[]>([])
const statusOpts=[{label:'在读',value:'在读'},{label:'停课',value:'停课'},{label:'结课',value:'结课'},{label:'转出',value:'转出'},{label:'退费',value:'退费'}]
const fmtH=(n:any)=>n==null||isNaN(n)?'—':n.toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:1})
const fmtM=(n:any)=>n==null||isNaN(n)?'—':Number(n).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:1})
const badgeClass=(s:string)=>({在读:'m-badge--accent',停课:'m-badge--amber',结课:'m-badge--gray',转出:'m-badge--red',退费:'m-badge--red'}[s]||'m-badge--gray')
/** 当前班级：真实班级关联在 classes 数组里（class_name 是旧字段，基本为空） */
const classLabel=(item:any)=>{
  const cs=item.classes||[]
  if(cs.length===0)return item.class_name||'暂无班级'
  return cs[0].name+(cs.length>1?` 等${cs.length}个班`:'')
}
const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}

const campusOptions=computed(()=>[{text:'全部校区',value:0},...campuses.value.map((c:any)=>({text:c.name,value:c.id}))])
const packageOptions=[{text:'全部课包',value:''},...PACKAGE_TYPES.map(p=>({text:p,value:p}))]

function goDetail(id:number){router.push(`/m/students/${id}`)}
async function load(reset=false){
  if(reset){page.value=1;fin.value=false;students.value=[]}
  ld.value=true
  try{
    const p:any={page:page.value,size:20}
    // 纯数字按手机号搜，否则按姓名搜
    if(kw.value)/^\d+$/.test(kw.value.trim())?p.parent_phone=kw.value.trim():p.name=kw.value
    if(filterStatus.value)p.status=filterStatus.value
    if(filterCampus.value)p.campus_id=filterCampus.value
    if(filterPackage.value)p.course_package=filterPackage.value
    const res:any=await getStudents(p)
    const list=res?.items??res?.data??[]
    if(reset)students.value=list;else students.value.push(...list)
    if(list.length<20)fin.value=true
    page.value++
  }catch{}finally{ld.value=false}
}
function loadMore(){load()};function onR(){refr.value=true;load(true).finally(()=>{refr.value=false})}

// ── 新增学生 ──
const showAdd=ref(false),saving=ref(false),showCampusPicker=ref(false)
const af=reactive({name:'',parent_phone:'',campus_id:0,gender:'',grade:'',school:'',parent_name:'',notes:''})
const afCampusLabel=computed(()=>campuses.value.find((c:any)=>c.id===af.campus_id)?.name||'')
const campusPickerCols=computed(()=>campuses.value.map((c:any)=>({text:c.name,value:c.id})))

function openAdd(){
  af.name='';af.parent_phone='';af.gender='';af.grade='';af.school='';af.parent_name='';af.notes=''
  af.campus_id=userStore.userInfo?.campus_id||campuses.value[0]?.id||0
  showAdd.value=true
}
function onCampusConfirm({selectedOptions}:any){if(selectedOptions?.[0])af.campus_id=selectedOptions[0].value;showCampusPicker.value=false}
async function saveAdd(){
  if(!af.campus_id){showToast('请选择校区');return}
  saving.value=true
  try{
    await createStudent({...af,enroll_date:today()})
    showToast('学生已添加')
    showAdd.value=false
    load(true)
  }catch{}finally{saving.value=false}
}

onMounted(async()=>{
  load(true)
  try{const c:any=await getCampuses();campuses.value=Array.isArray(c)?c:[]}catch{}
})
</script>
