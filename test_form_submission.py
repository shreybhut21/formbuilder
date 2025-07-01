import pytest
import json
from form import app, get_db

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_create_form_and_submit_all_fields(client):
    # Define form fields with all types and attributes
    form_fields = [
        {
            "label": "Text Field",
            "name": "text_field",
            "type": "text",
            "placeholder": "Enter text",
            "required": True,
            "minlength": "2",
            "maxlength": "10",
            "description": "Help text for text",
            "value": "default text",
        },
        {
            "label": "Number Field",
            "name": "number_field",
            "type": "number",
            "placeholder": "Enter number",
            "required": False,
            "min": "1",
            "max": "100",
            "description": "Help text for number",
            "value": "50",
        },
        {
            "label": "Textarea Field",
            "name": "textarea_field",
            "type": "textarea",
            "placeholder": "Enter long text",
            "required": False,
            "description": "Help text for textarea",
            "value": "default long text",
        },
        {
            "label": "Radio Field",
            "name": "radio_field",
            "type": "radio",
            "options": ["Option1", "Option2"],
            "required": True,
            "description": "Help text for radio",
            "value": "Option1",
        },
        {
            "label": "Checkbox Field",
            "name": "checkbox_field",
            "type": "checkbox",
            "options": ["Check1", "Check2"],
            "required": False,
            "description": "Help text for checkbox",
            "value": "Check1,Check2",
        },
        {
            "label": "Select Field",
            "name": "select_field",
            "type": "select",
            "options": ["Select1", "Select2"],
            "required": True,
            "description": "Help text for select",
            "value": "Select2",
        },
        {
            "label": "Email Field",
            "name": "email_field",
            "type": "email",
            "placeholder": "Enter email",
            "required": True,
            "description": "Help text for email",
            "value": "test@example.com",
        },
        {
            "label": "Password Field",
            "name": "password_field",
            "type": "password",
            "placeholder": "Enter password",
            "required": True,
            "description": "Help text for password",
            "value": "secret",
        },
        {
            "label": "URL Field",
            "name": "url_field",
            "type": "url",
            "placeholder": "Enter URL",
            "required": False,
            "description": "Help text for url",
            "value": "https://example.com",
        },
        {
            "label": "Range Field",
            "name": "range_field",
            "type": "range",
            "min": "0",
            "max": "10",
            "required": False,
            "description": "Help text for range",
            "value": "5",
        },
    ]
    
    # Create form
    response = client.post(
        "/create_form",
        data={
            "form_title": "Test Form All Fields",
            "form_description": "Description for test form",
            "user_name": "Tester",
            "form_fields": json.dumps(form_fields),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    # Extract form_id from DB
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM submissions WHERE form_title=?", ("Test Form All Fields",))
        form_id = c.fetchone()[0]

    # Submit form data
    form_data = {
        "form_id": str(form_id),
        "form_title": "Test Form All Fields",
        "user": "Tester",
        "form_description": "Description for test form",
        "text_field": "Hello",
        "number_field": "42",
        "textarea_field": "Long text here",
        "radio_field": "Option1",
        "checkbox_field": "Check1,Check2",
        "select_field": "Select2",
        "form_structure": json.dumps(form_fields),
    }
    response = client.post("/submit_form", data=form_data, follow_redirects=True)
    assert response.status_code == 200

    # Get latest response id
    with get_db() as conn:
        c = conn.cursor()
        table_name = f"form_{form_id}_responses"
        c.execute(f"SELECT id FROM {table_name} ORDER BY submitted_at DESC LIMIT 1")
        response_id = c.fetchone()[0]

    # Access edit_submission page to verify prefill
    response = client.get(f"/edit_submission/{form_id}/{response_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # Check some prefilled values in html
    assert "value=\"Hello\"" in html
    assert "value=\"42\"" in html
    assert "Long text here" in html
    assert "checked" in html  # for radio and checkbox
    assert "Select2" in html
