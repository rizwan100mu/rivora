"""Authenticated opt-in live tracking; independent of attendance."""
import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate
SESSION = 'Rivora Mobile Tracking Session'
POINT = 'Rivora Mobile Location Point'

def ensure_indexes():
    """Keep scoped latest-point and dated-route reads indexed as history grows."""
    if frappe.db.table_exists(POINT):
        frappe.db.add_index(POINT, ['employee', 'captured_at'], index_name='rivora_mobile_location_employee_capture')

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def employee():
    if frappe.session.user == 'Guest':
        frappe.throw(_('Sign in required'), frappe.PermissionError)
    row = frappe.db.get_value('Employee', {'user_id': frappe.session.user, 'status': 'Active'}, ['name','company','employee_name'], as_dict=True)
    if not row:
        frappe.throw(_('An active linked employee is required'), frappe.PermissionError)
    return row

def enabled():
    if not cint(frappe.db.get_single_value('Rivora Mobile Settings', 'enable_live_location')):
        frappe.throw(_('Live location is disabled in Rivora Mobile Settings'), frappe.PermissionError)

def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{48}', value):
        frappe.throw(_('Invalid location event or device ID'))
    return value

def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        frappe.throw(_('A valid UTC capture timestamp is required'))

def coordinates(point, current):
    try:
        lat, lon, accuracy = (float(point[k]) for k in ('latitude','longitude','accuracy'))
        if not all(math.isfinite(v) for v in (lat, lon, accuracy)) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0 <= accuracy <= 1000:
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError):
        frappe.throw(_('Invalid coordinates or accuracy'))
    captured = timestamp(point.get('captured_at'))
    if captured > current + timedelta(minutes=2) or captured < current - timedelta(hours=24):
        frappe.throw(_('Capture time is outside the accepted window'))
    if point.get('mocked') not in (None, False, 0):
        frappe.throw(_('Mock locations are not accepted'))
    return lat, lon, accuracy, captured

@frappe.whitelist(methods=['GET'])
def policy():
    if frappe.session.user == 'Guest':
        frappe.throw(_('Sign in required'), frappe.PermissionError)
    own = frappe.db.get_value('Employee', {'user_id': frappe.session.user, 'status': 'Active'}, ['name','company','employee_name'], as_dict=True)
    if not own and not set(frappe.get_roles()).intersection({'System Manager','HR Manager'}):
        frappe.throw(_('An active linked employee is required'), frappe.PermissionError)
    return {'enabled': bool(cint(frappe.db.get_single_value('Rivora Mobile Settings','enable_live_location'))), 'employee': own.name if own else None, 'can_share': bool(own), 'interval_seconds':10, 'session_hours':8, 'retention_days':7}

def owned_session(session_id, device_id):
    own = employee()
    doc = frappe.get_doc(SESSION, session_id)
    if doc.employee != own.name or doc.user != frappe.session.user or doc.device_id != device_id:
        frappe.throw(_('Tracking session does not belong to this device'), frappe.PermissionError)
    return doc

@frappe.whitelist(methods=['POST'])
def start(device_id, event_id):
    own = employee()
    enabled()
    key(device_id)
    key(event_id)
    name = hashlib.sha256(f'{own.name}:{event_id}'.encode()).hexdigest()
    if frappe.db.exists(SESSION,name):
        doc = owned_session(name,device_id)
        return {'session_id':name,'expires_at':doc.expires_at,'active':bool(doc.active) and now() < get_datetime(doc.expires_at)}
    current = now()
    doc = frappe.get_doc({'doctype':SESSION,'session_key':name,'employee':own.name,'company':own.company,'user':frappe.session.user,'device_id':device_id,'active':1,'started_at':current,'expires_at':current+timedelta(hours=8)})
    doc.insert(ignore_permissions=True)
    return {'session_id':doc.name,'expires_at':doc.expires_at,'active':True}

@frappe.whitelist(methods=['POST'])
def stop(session_id, device_id):
    employee()
    if not frappe.db.exists(SESSION,session_id):
        return {'stopped':True}
    doc = owned_session(session_id,device_id)
    if doc.active:
        doc.active=0
        doc.stopped_at=now()
        doc.save(ignore_permissions=True)
    return {'stopped':True}

@frappe.whitelist(methods=['POST'])
def upload(session_id, device_id, points):
    enabled()
    doc = owned_session(session_id,device_id)
    points = frappe.parse_json(points)
    if not isinstance(points,list) or not 1 <= len(points) <= 100:
        frappe.throw(_('Send between 1 and 100 location points'))
    current=now()
    receipts=[]
    for index,point in enumerate(points):
        savepoint=f'location_point_{index}'
        frappe.db.savepoint(savepoint)
        try:
            if not isinstance(point,dict):
                frappe.throw(_('Invalid location point'))
            event=key(point.get('event_id'))
            lat,lon,accuracy,captured=coordinates(point,current)
            end=get_datetime(doc.stopped_at or doc.expires_at)
            if captured < get_datetime(doc.started_at) or captured > min(end,get_datetime(doc.expires_at)):
                frappe.throw(_('Point captured outside tracking session'))
            point_id=hashlib.sha256(f'{doc.name}:{event}'.encode()).hexdigest()
            if not frappe.db.exists(POINT,point_id):
                frappe.get_doc({'doctype':POINT,'event_key':point_id,'tracking_session':doc.name,'employee':doc.employee,'company':doc.company,'captured_at':captured,'received_at':current,'latitude':lat,'longitude':lon,'accuracy':accuracy}).insert(ignore_permissions=True)
            receipts.append({'event_id':event,'status':'accepted'})
        except frappe.ValidationError:
            frappe.db.rollback(save_point=savepoint)
            receipts.append({'event_id':point.get('event_id') if isinstance(point,dict) else None,'status':'rejected','reason':'Invalid point or capture outside tracking session'})
    return {'receipts':receipts}

def visible_employees():
    if frappe.session.user == 'Guest':
        frappe.throw(_('Sign in required'), frappe.PermissionError)
    own=frappe.db.get_value('Employee', {'user_id':frappe.session.user,'status':'Active'},
                            ['name','company','employee_name'],as_dict=True)
    manager=bool(set(frappe.get_roles()).intersection({'System Manager','HR Manager'}))
    if not own and not manager:
        frappe.throw(_('An active linked employee is required'),frappe.PermissionError)
    filters={'status':'Active'}
    if not manager:
        filters['reports_to']=own.name
    try:
        team=frappe.get_list('Employee',filters=filters,fields=['name','employee_name','company'],page_length=500)
    except frappe.PermissionError:
        team=[]
    rows=([own] if own else [])+team
    return {row.name:row for row in rows[:500]}

@frappe.whitelist(methods=['GET'])
def latest():
    enabled()
    current=now()
    result=[]
    visible=visible_employees()
    if not visible:
        return {'employees':[], 'server_time':current, 'limit':500}
    # One scoped query instead of one point/session query for every employee.
    rows=frappe.db.sql("""
        SELECT p.employee, p.latitude, p.longitude, p.accuracy, p.captured_at,
               p.received_at, s.active, s.expires_at
        FROM `tabRivora Mobile Location Point` p
        INNER JOIN (
            SELECT employee, MAX(captured_at) AS captured_at
            FROM `tabRivora Mobile Location Point`
            WHERE employee IN %(employees)s GROUP BY employee
        ) newest ON newest.employee=p.employee AND newest.captured_at=p.captured_at
        INNER JOIN `tabRivora Mobile Tracking Session` s ON s.name=p.tracking_session
        WHERE p.employee IN %(employees)s
        ORDER BY p.employee, p.name DESC
    """, {'employees':tuple(visible)}, as_dict=True)
    latest_points={}
    for point in rows:
        latest_points.setdefault(point.employee,point)
    for name,row in visible.items():
        point=latest_points.get(name)
        data={'employee':name,'employee_name':row.employee_name,'company':row.company,'status':'unavailable'}
        if point:
            age=max(0,int((current-get_datetime(point.captured_at)).total_seconds()))
            data.update({k:point[k] for k in ('latitude','longitude','accuracy','captured_at','received_at')})
            data['age_seconds']=age
            data['status']='stopped' if not point.active or current > get_datetime(point.expires_at) else 'recent' if age <= 180 else 'stale'
        result.append(data)
    return {'employees':result,'server_time':current,'limit':500}

@frappe.whitelist(methods=['GET'])
def route(employee_id,date=None):
    enabled()
    if employee_id not in visible_employees():
        frappe.throw(_('Employee is outside your permitted team'),frappe.PermissionError)
    day=getdate(date) if date else now().date()
    if day < (now()-timedelta(days=7)).date() or day > now().date():
        frappe.throw(_('Choose a date within the last seven UTC days'))
    start_at=datetime.combine(day,datetime.min.time())
    points=frappe.get_all(POINT,filters={'employee':employee_id,'captured_at':('between',[start_at,start_at+timedelta(days=1)-timedelta(microseconds=1)])},fields=['latitude','longitude','accuracy','captured_at'],order_by='captured_at asc, name asc',limit_page_length=2001)
    return {'points':points[:2000],'date':str(day),'timezone':'UTC','truncated':len(points)>2000}

def cleanup():
    cutoff=now()-timedelta(days=7)
    frappe.db.delete(POINT,{'captured_at':('<',cutoff)})
    frappe.db.delete(SESSION,{'expires_at':('<',cutoff)})
