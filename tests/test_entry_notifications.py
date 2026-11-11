import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

class EntryAlertTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(sys.modules)
        self.settings={'enable_entry_notifications':1,'entry_notification_doctypes':[{'document_type':'Sales Order'}],'entry_rivora_notification_users':[{'user':'allowed'},{'user':'denied'},{'user':'disabled'}]}
        self.doc=types.SimpleNamespace(doctype='Sales Order',name='SO-1',creation='2026-10-29 12:00:00',owner='allowed',meta=types.SimpleNamespace(istable=0,issingle=0))
        self.doc.get=lambda k: getattr(self.doc,k,None)
        self.logs={};self.readable={'allowed'};self.personal_disabled=set()
        f=types.ModuleType('frappe');f._=lambda v:v;f.flags={};f.DuplicateEntryError=type('DuplicateEntryError',(Exception,),{})
        f.throw=lambda message:(_ for _ in ()).throw(ValueError(message))
        f.get_cached_doc=Mock(side_effect=lambda *args:self.settings)
        f.get_meta=Mock(return_value=self.doc.meta)
        f.db=types.SimpleNamespace(exists=Mock(side_effect=self.exists),get_value=Mock(side_effect=lambda dt,name,field:0 if name=='disabled' else 1))
        f.has_permission=Mock(side_effect=lambda dt,ptype,doc,user:user in self.readable)
        f.get_doc=Mock(side_effect=self.get_doc);f.enqueue=Mock();f.log_error=Mock()
        sys.modules['frappe']=f;self.f=f
        notify=types.ModuleType('frappe.desk.doctype.notification_settings.notification_settings')
        notify.is_notifications_enabled=lambda user:user not in self.personal_disabled
        sys.modules[notify.__name__]=notify
        scope_spec=importlib.util.spec_from_file_location('rivora.notification_scope',Path(__file__).parents[1]/'rivora/notification_scope.py')
        scope=importlib.util.module_from_spec(scope_spec);scope_spec.loader.exec_module(scope)
        sys.modules['rivora.notification_scope']=scope
        spec=importlib.util.spec_from_file_location('rivora.entry_alert_test_target',Path(__file__).parents[1]/'rivora/entry_notifications.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
    def tearDown(self):
        for key in list(sys.modules):
            if key not in self.saved:sys.modules.pop(key,None)
        sys.modules.update(self.saved)
    def exists(self,doctype,name):
        if doctype=='Notification Log':return name in self.logs
        if doctype=='DocType':return True
        return doctype==self.doc.doctype and name==self.doc.name
    def get_doc(self,arg,name=None):
        if not isinstance(arg,dict):return self.doc
        def insert(**kwargs):
            key=kwargs['set_name']
            if key in self.logs:raise self.f.DuplicateEntryError()
            self.logs[key]=dict(arg)
        return types.SimpleNamespace(insert=insert)
    def deliver(self):self.module.deliver_entry_alert(self.doc.doctype,self.doc.name,str(self.doc.creation))
    def test_disabled_settings_do_not_queue(self):
        self.settings['enable_entry_notifications']=0
        self.module.queue_entry_alert(self.doc);self.f.enqueue.assert_not_called()
    def test_unselected_document_does_not_queue(self):
        self.doc.doctype='Quotation';self.module.queue_entry_alert(self.doc);self.f.enqueue.assert_not_called()
    def test_queues_after_commit_without_mutating_business_document(self):
        before=vars(self.doc).copy();self.module.queue_entry_alert(self.doc)
        args=self.f.enqueue.call_args.kwargs
        self.assertTrue(args['enqueue_after_commit']);self.assertEqual(args['doctype'],'Sales Order')
        self.assertEqual(vars(self.doc),before);self.assertFalse(self.logs)
    def test_no_recipients_does_not_queue(self):
        self.settings['entry_rivora_notification_users']=[];self.module.queue_entry_alert(self.doc);self.f.enqueue.assert_not_called()
    def test_log_and_child_documents_do_not_recurse(self):
        for name in ['Notification Log','Error Log','Rivora Mobile Settings']:
            self.doc.doctype=name;self.module.queue_entry_alert(self.doc)
        self.doc.doctype='Sales Order Item';self.doc.meta.istable=1;self.module.queue_entry_alert(self.doc)
        self.f.get_cached_doc.assert_not_called();self.f.enqueue.assert_not_called()
    def test_migration_skips_queue(self):
        self.f.flags['in_migrate']=True;self.module.queue_entry_alert(self.doc);self.f.enqueue.assert_not_called()
    def test_enqueue_failure_does_not_break_business_insert(self):
        self.f.enqueue.side_effect=RuntimeError('offline')
        self.module.queue_entry_alert(self.doc);self.f.log_error.assert_called_once()
    def test_only_selected_enabled_readable_user_receives_alert(self):
        self.deliver();self.assertEqual(len(self.logs),1)
        alert=next(iter(self.logs.values()));self.assertEqual(alert['for_user'],'allowed')
        self.assertEqual(alert['document_name'],'SO-1');self.assertEqual(alert['subject'],'New Sales Order: SO-1')
    def test_creator_can_receive_when_explicitly_selected_and_retry_is_idempotent(self):
        self.settings['entry_rivora_notification_users'].append({'user':'allowed'})
        self.deliver();self.deliver();self.assertEqual(len(self.logs),1)
    def test_permission_revocation_prevents_delivery(self):
        self.readable.clear();self.deliver();self.assertFalse(self.logs)
    def test_personal_notification_optout_is_respected(self):
        self.personal_disabled.add('allowed');self.deliver();self.assertFalse(self.logs)
    def test_disabling_settings_before_worker_runs_prevents_delivery(self):
        self.module.queue_entry_alert(self.doc);self.settings['enable_entry_notifications']=0
        self.deliver();self.assertFalse(self.logs)
    def test_recreated_record_with_same_name_does_not_use_old_job(self):
        self.module.deliver_entry_alert('Sales Order','SO-1','old creation');self.assertFalse(self.logs)
    def test_multiple_selected_doctypes_and_users(self):
        self.settings['entry_notification_doctypes'].append({'document_type':'Quotation'})
        self.settings['entry_rivora_notification_users'].append({'user':'second'})
        self.readable.add('second');self.doc.doctype='Quotation';self.deliver()
        self.assertEqual({d['for_user'] for d in self.logs.values()},{'allowed'})
    def test_enabled_configuration_requires_users_and_doctypes(self):
        self.settings['entry_rivora_notification_users']=[]
        with self.assertRaises(ValueError):self.module.validate_settings(self.settings)
    def test_invalid_recipient_or_log_selection_is_rejected(self):
        self.settings['entry_rivora_notification_users']=[{'user':'Guest'}]
        with self.assertRaises(ValueError):self.module.validate_settings(self.settings)
        self.settings['entry_rivora_notification_users']=[{'user':'allowed'}]
        self.settings['entry_notification_doctypes']=[{'document_type':'Notification Log'}]
        with self.assertRaises(ValueError):self.module.validate_settings(self.settings)

if __name__=='__main__':unittest.main()
