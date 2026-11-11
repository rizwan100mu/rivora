import importlib.util
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock

class Row(dict):
    def __getattr__(self,k):return self.get(k)
    def __setattr__(self,k,v):self[k]=v

class LocationTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(sys.modules)
        self.current=datetime(2026,11,7,10)
        self.own=Row(name='EMP-1',company='A',employee_name='Worker')
        self.session=Row(name='SESSION',employee='EMP-1',company='A',user='worker',device_id='d'*48,started_at=self.current-timedelta(minutes=5),expires_at=self.current+timedelta(hours=8),stopped_at=None,active=1)
        self.session.save=Mock()
        self.points={};self.created=[];self.team=[];self.roles=[]
        f=types.ModuleType('frappe');f.whitelist=lambda **kw:lambda fn:fn;f._=lambda text:text
        f.ValidationError=type('ValidationError',(Exception,),{});f.PermissionError=PermissionError
        f.throw=lambda text,kind=None:(_ for _ in ()).throw((kind or f.ValidationError)(text))
        f.session=Row(user='worker');f.parse_json=lambda v:v
        def get_value(dt,name,fields,**kwargs):return self.own
        f.db=types.SimpleNamespace(get_value=Mock(side_effect=get_value),get_single_value=Mock(return_value=1),exists=Mock(side_effect=lambda dt,name:(dt=='Rivora Mobile Tracking Session' and name=='SESSION') or name in self.points),savepoint=Mock(),rollback=Mock(),delete=Mock(),sql=Mock(return_value=[]))
        def get_doc(arg,name=None):
            if not isinstance(arg,dict):return self.session
            doc=Row(arg)
            doc.name=arg.get('event_key') or arg.get('session_key')
            def insert(**kw):
                if doc.doctype=='Rivora Mobile Location Point':self.points[doc.name]=doc
                self.created.append(doc)
            doc.insert=Mock(side_effect=insert)
            return doc
        f.get_doc=Mock(side_effect=get_doc);f.get_roles=Mock(side_effect=lambda:self.roles)
        f.get_list=Mock(side_effect=lambda *a,**kw:self.team);f.get_all=Mock(return_value=[])
        sys.modules['frappe']=f
        u=types.ModuleType('frappe.utils');u.cint=lambda x:int(x or 0)
        u.get_datetime=lambda v:v if isinstance(v,datetime) else datetime.fromisoformat(v)
        u.getdate=lambda v:datetime.fromisoformat(v).date()
        sys.modules['frappe.utils']=u
        spec=importlib.util.spec_from_file_location('location_test',Path(__file__).parents[1]/'rivora/live_location.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.module.now=lambda:self.current;self.f=f
    def tearDown(self):
        for key in list(sys.modules):
            if key not in self.saved:sys.modules.pop(key,None)
        sys.modules.update(self.saved)
    def point(self,**kw):return dict(event_id='a'*48,latitude=0,longitude=0,accuracy=10,captured_at='2026-11-07T09:59:00Z',**kw)
    def upload(self,points):return self.module.upload('SESSION','d'*48,points)['receipts']
    def test_zero_coordinates_are_valid_and_employee_is_server_bound(self):
        p=self.point();p['employee']='OTHER';p['company']='OTHER'
        self.assertEqual(self.upload([p])[0]['status'],'accepted')
        row=next(iter(self.points.values()));self.assertEqual(row.employee,'EMP-1');self.assertEqual(row.company,'A');self.assertEqual(row.latitude,0)
    def test_admin_can_view_policy_without_a_linked_employee_but_cannot_start_sharing(self):
        self.own=None;self.roles=['System Manager']
        result=self.module.policy()
        self.assertTrue(result['enabled']);self.assertFalse(result['can_share'])
        self.assertIsNone(result['employee']);self.assertEqual(result['interval_seconds'],10)
        with self.assertRaises(PermissionError):self.module.start('d'*48,'a'*48)
    def test_unlinked_non_manager_cannot_open_tracking_policy(self):
        self.own=None;self.roles=['Employee']
        with self.assertRaises(PermissionError):self.module.policy()
    def test_guest_cannot_open_tracking_policy(self):
        self.f.session.user='Guest'
        with self.assertRaises(PermissionError):self.module.policy()
    def test_history_reads_have_employee_capture_time_index(self):
        self.f.db.table_exists=Mock(return_value=True);self.f.db.add_index=Mock()
        self.module.ensure_indexes()
        self.f.db.add_index.assert_called_once_with('Rivora Mobile Location Point',['employee','captured_at'],index_name='rivora_mobile_location_employee_capture')
    def test_batch_has_per_point_receipts_and_retry_does_not_duplicate(self):
        p=self.point();bad={**p,'event_id':'b'*48,'latitude':999};third={**p,'event_id':'c'*48}
        result=self.upload([p,bad,third]);self.assertEqual([r['status'] for r in result],['accepted','rejected','accepted'])
        self.upload([p,third]);self.assertEqual(len(self.points),2)
        self.f.db.rollback.assert_called_once()
    def test_nonfinite_ranges_future_old_mock_and_naive_timestamps_reject(self):
        for patch in [{'latitude':float('nan')},{'longitude':181},{'accuracy':-1},{'captured_at':'2026-11-07T11:00:00Z'},{'captured_at':'2026-11-05T10:00:00Z'},{'captured_at':'2026-11-07T09:59:00'},{'mocked':True}]:
            with self.subTest(patch=patch):self.assertEqual(self.upload([{**self.point(),**patch}])[0]['status'],'rejected')
        self.assertFalse(self.points)
    def test_another_device_user_or_employee_cannot_upload_or_stop(self):
        for patch in [{'device_id':'x'*48},{'user':'other'},{'employee':'OTHER'}]:
            original=dict(self.session);self.session.update(patch)
            with self.assertRaises(PermissionError):self.upload([self.point()])
            with self.assertRaises(PermissionError):self.module.stop('SESSION','d'*48)
            self.session.clear();self.session.update(original)
    def test_guest_and_disabled_policy_reject_before_write(self):
        self.f.session.user='Guest'
        with self.assertRaises(PermissionError):self.module.policy()
        self.f.session.user='worker';self.f.db.get_single_value.return_value=0
        with self.assertRaises(PermissionError):self.upload([self.point()])
        self.assertFalse(self.points)
    def test_stop_allows_old_outbox_but_rejects_points_captured_after_stop(self):
        self.session.active=0;self.session.stopped_at=self.current-timedelta(seconds=30)
        self.assertEqual(self.upload([self.point()])[0]['status'],'accepted')
        self.assertEqual(self.upload([{**self.point(),'event_id':'c'*48,'captured_at':'2026-11-07T10:00:00Z'}])[0]['status'],'rejected')
    def test_expiry_and_start_time_enforced(self):
        self.session.expires_at=self.current-timedelta(minutes=2)
        self.assertEqual(self.upload([self.point()])[0]['status'],'rejected')
        self.session.started_at=self.current
        self.assertEqual(self.upload([self.point()])[0]['status'],'rejected')
    def test_manager_scope_uses_employee_permissions_and_direct_reports(self):
        self.team=[Row(name='EMP-2',company='A',employee_name='Report')]
        visible=self.module.visible_employees()
        self.assertEqual(set(visible),{'EMP-1','EMP-2'})
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'status':'Active','reports_to':'EMP-1'})
        self.roles=['HR Manager'];self.module.visible_employees()
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'status':'Active'})
    def test_employee_permission_failure_falls_back_to_self_only(self):
        self.f.get_list.side_effect=PermissionError()
        self.assertEqual(set(self.module.visible_employees()),{'EMP-1'})
    def test_unauthorized_route_fails_before_reading_points(self):
        with self.assertRaises(PermissionError):self.module.route('OTHER')
        self.f.get_all.assert_not_called()
    def test_route_is_bounded_by_employee_and_utc_day(self):
        self.module.route('EMP-1','2026-11-07')
        filters=self.f.get_all.call_args.kwargs['filters'];self.assertEqual(filters['employee'],'EMP-1')
        self.assertEqual(filters['captured_at'][1][0],datetime(2026,11,7))
        self.assertEqual(self.f.get_all.call_args.kwargs['limit_page_length'],2001)
    def test_start_is_employee_bound_and_expires_in_eight_hours(self):
        result=self.module.start('d'*48,'a'*48)
        self.assertEqual(result['expires_at'],self.current+timedelta(hours=8))
        self.assertEqual(self.created[-1].employee,'EMP-1')
    def test_latest_marks_recent_stale_and_stopped(self):
        p=Row(employee='EMP-1',active=1,expires_at=self.session.expires_at,latitude=0,longitude=0,accuracy=10,captured_at=self.current-timedelta(seconds=60),received_at=self.current,tracking_session='SESSION')
        self.f.db.sql.return_value=[p]
        self.assertEqual(self.module.latest()['employees'][0]['status'],'recent')
        p.captured_at=self.current-timedelta(minutes=5)
        self.assertEqual(self.module.latest()['employees'][0]['status'],'stale')
        p.active=0
        self.assertEqual(self.module.latest()['employees'][0]['status'],'stopped')
    def test_hr_desk_viewer_without_linked_employee_can_view_permitted_team(self):
        self.f.db.get_value.side_effect=lambda *a,**kw:None
        self.roles=['HR Manager'];self.team=[Row(name='EMP-2',company='A',employee_name='Report')]
        self.assertEqual(set(self.module.visible_employees()),{'EMP-2'})
        with self.assertRaises(PermissionError):self.module.start('d'*48,'a'*48)
    def test_unlinked_ordinary_user_cannot_view_team(self):
        self.f.db.get_value.side_effect=lambda *a,**kw:None
        with self.assertRaises(PermissionError):self.module.visible_employees()
    def test_manager_with_no_employee_read_scope_gets_empty_without_sql(self):
        self.f.db.get_value.side_effect=lambda *a,**kw:None
        self.roles=['System Manager'];self.f.get_list.side_effect=PermissionError()
        self.assertEqual(self.module.latest()['employees'],[])
        self.f.db.sql.assert_not_called()
    def test_cleanup_only_telemetry_and_seven_day_cutoff(self):
        self.module.cleanup();calls=self.f.db.delete.call_args_list
        self.assertEqual([c.args[0] for c in calls],['Rivora Mobile Location Point','Rivora Mobile Tracking Session'])
        self.assertEqual(calls[0].args[1]['captured_at'][1],self.current-timedelta(days=7))

if __name__=='__main__':unittest.main()
