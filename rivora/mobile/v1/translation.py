import frappe

from rivora.mobile.v1.api_utils import (
    employee_validate,
    exception_handler,
    gen_response,
    get_employee_settings,
)


@frappe.whitelist()
@employee_validate(methods=["GET"])
def get_rivora_language():
    try:
        employee_settings = get_employee_settings()
        data = []
        for row in employee_settings.get("rivora_language"):
            data.append(
                dict(
                    language=row.get("language"),
                    direction=row.get("direction"),
                    language_name=row.get("language_name"),
                )
            )
        return gen_response(200, "Language Get Successfully", data)
    except Exception as e:
        return exception_handler(e)


@frappe.whitelist()
@employee_validate(methods=["GET"])
def get_translation(language):
    try:
        if not language:
            return gen_response(500, "Language is required.")

        rivora_language_data = frappe.get_value(
            "Rivora Language",
            {"language": language},
            ["language"],
            as_dict=1,
        )
        if not rivora_language_data:
            return gen_response(500, "Invalid Language.")
        translation_doc = frappe.get_all(
            "Rivora Translation",
            filters={"language": language},
            fields=["source_text", "translated_text"],
        )
        translation_data = {}
        for translation in translation_doc:
            translation_data[translation.get("source_text")] = translation.get(
                "translated_text"
            ) or translation.get("source_text")
        return gen_response(
            200,
            "Translation retrieved successfully",
            {
                "translation_data": translation_data,
            },
        )
    except Exception as e:
        return exception_handler(e)
