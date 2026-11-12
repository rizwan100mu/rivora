import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

class PushHookTests(unittest.TestCase):
    def setUp(self):
        source=ast.parse((Path(__file__).parents[1]/"rivora/api.py").read_text(encoding="utf-8"))
        hook=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=="push_update")
        self.f=types.SimpleNamespace(enqueue=Mock(),db=types.SimpleNamespace(delete=Mock()))
        scope={"frappe":self.f}
        exec(compile(ast.Module(body=[hook],type_ignores=[]),"push_hook","exec"),scope)
        self.hook=scope["push_update"]

    def test_saved_notification_reference_queued_after_commit(self):
        self.hook({"name":"LOG-1","for_user":"me@example.com"})
        self.f.enqueue.assert_called_once_with("rivora.api.send_push",queue="short",enqueue_after_commit=True,user="me@example.com",notification_name="LOG-1")

    def test_no_recipient_does_not_queue(self):
        self.hook({"name":"LOG-1"})
        self.f.enqueue.assert_not_called()

    def test_no_saved_name_does_not_queue(self):
        self.hook({"for_user":"me@example.com"})
        self.f.enqueue.assert_not_called()

    def test_native_todo_assignment_uses_desk_notification(self):
        self.hook({"name":"LOG-1","for_user":"me@example.com","type":"Assignment","document_type":"ToDo"})
        self.f.enqueue.assert_called()
        self.f.db.delete.assert_not_called()

    def test_business_document_assignments_forward_the_desk_log(self):
        for doctype in ['Quotation', 'Task', 'Administrative Decision', 'Custom DocType']:
            self.hook({"name":"LOG-1","for_user":"creator@example.com","type":"Assignment","document_type":doctype})
        self.f.enqueue.assert_called()
        self.f.db.delete.assert_not_called()

    def test_saved_assignment_names_are_forwarded(self):
        self.hook({"name":"rivora-todo-123","for_user":"me@example.com","type":"Assignment","document_type":"ToDo"})
        self.f.enqueue.assert_called_once()

if __name__ == "__main__":unittest.main()
