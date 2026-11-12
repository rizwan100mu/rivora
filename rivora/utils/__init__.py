import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.core.doctype.file.file import extract_images_from_html
from frappe.desk.form.document_follow import follow_document
from frappe.utils import cint, getdate, today


def get_holiday_list_for_employee(employee, raise_exception=True):
    if employee:
        holiday_list, company = frappe.get_cached_value(
            "Employee", employee, ["holiday_list", "company"]
        )
    else:
        holiday_list = ""
        company = frappe.db.get_single_value("Global Defaults", "default_company")

    if not holiday_list:
        holiday_list = frappe.get_cached_value(
            "Company", company, "default_holiday_list"
        )

    if not holiday_list and raise_exception:
        frappe.throw(
            _(
                "Please set a default Holiday List for Employee {0} or Company {1}"
            ).format(employee, company)
        )

    return holiday_list


def is_holiday(
    employee,
    date=None,
    raise_exception=True,
    only_non_weekly=False,
    with_description=False,
):
    """
    Returns True if given Employee has an holiday on the given date
                    :param employee: Employee `name`
                    :param date: Date to check. Will check for today if None
                    :param raise_exception: Raise an exception if no holiday list found, default is True
                    :param only_non_weekly: Check only non-weekly holidays, default is False
    """

    holiday_list = get_holiday_list_for_employee(employee, raise_exception)
    if not date:
        date = today()

    if not holiday_list:
        return False

    filters = {"parent": holiday_list, "holiday_date": date}
    if only_non_weekly:
        filters["weekly_off"] = False

    holidays = frappe.get_all(
        "Holiday", fields=["description"], filters=filters, pluck="description"
    )

    if with_description:
        return len(holidays) > 0, holidays

    return len(holidays) > 0


def get_employees_having_an_event_today(event_type, date=None):
    if event_type == "birthday":
        condition_column = "date_of_birth"
    elif event_type == "work_anniversary":
        condition_column = "date_of_joining"
    else:
        return

    employees_born_today = frappe.db.multisql(
        {
            "mariadb": f"""
			SELECT `name` as 'emp_id',`personal_email`, `company`, `company_email`, `user_id`, `employee_name` AS 'name', `image`, `date_of_joining`
			FROM `tabEmployee`
			WHERE
				DAY({condition_column}) = DAY(%(today)s)
			AND
				MONTH({condition_column}) = MONTH(%(today)s)
			AND
				`status` = 'Active'
		""",
            "postgres": f"""
			SELECT "name" AS 'emp_id',"personal_email", "company", "company_email", "user_id", "employee_name" AS 'name', "image"
			FROM "tabEmployee"
			WHERE
				DATE_PART('day', {condition_column}) = date_part('day', %(today)s)
			AND
				DATE_PART('month', {condition_column}) = date_part('month', %(today)s)
			AND
				"status" = 'Active'
		""",
        },
        dict(today=getdate(date), condition_column=condition_column),
        as_dict=1,
    )
    return employees_born_today


def notification_log(
    notification_name,
    doctype,
    subject,
    message,
    recipient,
    token,
    reference_doctype=None,
    reference_name=None,
    other_info=None,
):
    """Compatibility adapter for employee events into the ERPNext Desk inbox."""
    from frappe.desk.doctype.notification_settings.notification_settings import is_notifications_enabled
    if not recipient or recipient == "Guest" or frappe.session.user == recipient:
        return
    if not frappe.db.get_value("User", recipient, "enabled") or not is_notifications_enabled(recipient):
        return
    if reference_doctype and reference_name:
        doc = frappe.get_doc(reference_doctype, reference_name)
        if not frappe.has_permission(reference_doctype, "read", doc=doc, user=recipient):
            return
    frappe.get_doc({
        "doctype": "Notification Log", "type": "Alert", "for_user": recipient,
        "from_user": frappe.session.user, "subject": subject,
        "email_content": message, "document_type": reference_doctype,
        "document_name": reference_name,
    }).insert(ignore_permissions=True)


def strip_and_clean_html(html_content):
    # Use BeautifulSoup for better handling of HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove unnecessary tags and attributes
    for tag in soup.find_all():
        if tag.name == "a":
            tag.string = tag.get_text()  # Preserve text for links
        elif tag.name == "span" and "mention" in tag.get("class", []):
            tag.unwrap()  # Keep the text, remove the tag
        else:
            tag.unwrap()  # Remove all other tags but keep the text

    return soup.get_text(strip=True)  # Get cleaned text


def add_employee_comment(
    reference_doctype, reference_name, content, comment_email, comment_by
):
    """allow any logged user to post a comment"""
    doc = frappe.get_doc(
        doctype="Comment",
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        comment_email=comment_email,
        comment_type="Comment",
        comment_by=comment_by,
    )
    reference_doc = frappe.get_doc(reference_doctype, reference_name)
    doc.content = extract_images_from_html(reference_doc, content, is_private=True)
    doc.insert(ignore_permissions=True)

    follow_document(doc.reference_doctype, doc.reference_name, frappe.session.user)
    return doc.as_dict()


@frappe.whitelist()
def clear_linked_device(employee):
    registered_device_id = frappe.db.get_value(
        "Rivora Employee Device Registration", {"employee": employee}, "name"
    )
    if registered_device_id:
        frappe.delete_doc("Rivora Employee Device Registration", registered_device_id)


@frappe.whitelist()
def is_device_button_enable(employee):
    if not cint(
        frappe.db.get_single_value(
            "Rivora Settings", "enable_device_restrictions"
        )
    ):
        return False

    return bool(
        frappe.db.exists("Rivora Employee Device Registration", {"employee": employee})
    )
