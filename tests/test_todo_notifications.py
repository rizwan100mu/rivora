import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class ToDoNotificationsTests(unittest.TestCase):
    def setUp(self):
        self.doc = types.SimpleNamespace(name='TODO-1', allocated_to='worker@example.com', modified='2026-11-11 12:00:00', status='Open', owner='manager@example.com')
        self.doc.get = lambda key: getattr(self.doc, key, None)
        self.doc.get_doc_before_save = Mock(return_value=None)
        self.logs = {}
        self.f = types.ModuleType('frappe')
        self.f._ = lambda text: text
        self.f.flags = {}
        self.f.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
        self.f.enqueue = Mock()
        self.f.log_error = Mock()
        self.f.has_permission = Mock(return_value=True)
        self.f.db = types.SimpleNamespace(exists=Mock(side_effect=self.exists), get_value=Mock(return_value=1))
        self.f.get_doc = Mock(side_effect=self.get_doc)
        self.patch = patch.dict(sys.modules, {'frappe': self.f})
        self.patch.start(); self.addCleanup(self.patch.stop)
        spec = importlib.util.spec_from_file_location('todo_notifications_check', Path(__file__).parents[1] / 'rivora/todo_notifications.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)

    def exists(self, doctype, name):
        if doctype == 'ToDo': return True
        if isinstance(name, dict): return False
        return name in self.logs

    def get_doc(self, arg, name=None):
        if not isinstance(arg, dict): return self.doc
        def insert(**kwargs): self.logs[kwargs['set_name']] = arg
        return types.SimpleNamespace(insert=insert)

    def deliver(self): self.module.deliver_assignment(self.doc.name, 'worker@example.com', str(self.doc.modified))

    def test_new_assignment_queues_after_commit_without_settings(self):
        self.module.queue_assignment(self.doc)
        self.assertTrue(self.f.enqueue.call_args.kwargs['enqueue_after_commit'])
        self.assertEqual(self.f.enqueue.call_args.kwargs['user'], 'worker@example.com')

    def test_ordinary_edits_do_not_queue(self):
        self.doc.get_doc_before_save.return_value = {'allocated_to': 'worker@example.com'}
        self.module.queue_assignment(self.doc)
        self.f.enqueue.assert_not_called()

    def test_reassignment_queues_for_new_assignee(self):
        self.doc.get_doc_before_save.return_value = {'allocated_to': 'old@example.com'}
        self.module.queue_assignment(self.doc)
        self.f.enqueue.assert_called_once()

    def test_any_linked_doctype_delivers_only_to_allocated_user(self):
        for doctype in ['Quotation', 'Task', 'Administrative Decision', 'Custom DocType']:
            with self.subTest(doctype=doctype):
                self.logs.clear()
                self.f.enqueue.reset_mock()
                self.doc.reference_type = doctype
                self.doc.reference_name = 'DOC-1'
                self.deliver()
                log = next(iter(self.logs.values()))
                self.assertEqual(log['recipient'], self.doc.allocated_to)
                self.assertEqual(log['reference_type'], doctype)
                self.assertEqual(self.f.enqueue.call_args.kwargs['user'], self.doc.allocated_to)
                self.assertNotEqual(log['recipient'], self.doc.owner)

    def test_no_allocated_user_never_queues(self):
        self.doc.allocated_to = None
        self.module.queue_assignment(self.doc)
        self.f.enqueue.assert_not_called()

    def test_default_notification_has_no_dependency_on_personal_notification_switch(self):
        self.deliver()
        self.assertEqual(len(self.logs), 1)
        log = next(iter(self.logs.values()))
        self.assertEqual(log['doctype'], 'Rivora Mobile Notification')
        self.assertEqual(log['recipient'], 'worker@example.com')
        self.assertEqual(log['document_type'], 'ToDo')
        self.f.enqueue.assert_called_once_with('rivora.api.send_push', queue='short',
            enqueue_after_commit=True, user='worker@example.com',
            notification_name=next(iter(self.logs)),
            notification_source='Rivora Mobile Notification')
        self.assertNotIn('Notification Log', [item['doctype'] for item in self.logs.values()])

    def test_repeated_job_is_idempotent_even_if_standard_assignment_exists(self):
        self.deliver(); self.deliver()
        self.assertEqual(len(self.logs), 1)
        self.logs.clear()
        self.deliver()
        self.assertEqual(len(self.logs), 1)

    def test_revoked_permissions_disabled_user_closed_or_reassigned_todo_do_not_notify(self):
        self.f.has_permission.return_value = False
        self.deliver(); self.assertFalse(self.logs)
        self.f.has_permission.return_value = True
        self.f.db.get_value.return_value = 0
        self.deliver(); self.assertFalse(self.logs)
        self.f.db.get_value.return_value = 1
        self.doc.status = 'Closed'
        self.deliver(); self.assertFalse(self.logs)
        self.doc.status = 'Open'; self.doc.allocated_to = 'other@example.com'
        self.deliver(); self.assertFalse(self.logs)

    def test_install_and_queue_failure_never_break_todo_save(self):
        self.f.flags['in_install'] = True
        self.module.queue_assignment(self.doc); self.f.enqueue.assert_not_called()
        self.f.flags.clear(); self.f.enqueue.side_effect = RuntimeError()
        self.module.queue_assignment(self.doc); self.f.log_error.assert_called_once()
