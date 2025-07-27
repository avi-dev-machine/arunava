# app.py
import os
import pandas as pd

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, SubmitField, TextAreaField, SelectField # Import SelectField
from wtforms.validators import DataRequired, NumberRange, Length, ValidationError
from datetime import datetime, date, timedelta
from sqlalchemy import func

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Context Processor to make datetime available in templates ---
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# Configuration
app.config['SECRET_KEY'] = 'your_super_secret_key_for_matri_dairies_app' # IMPORTANT: Change this to a strong, unique key!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///matri_dairies.db' # Specific database file for this app
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# --- Define your dairy products and their prices ---
# This dictionary will be used to populate the dropdown and for autofill.
DAIRY_PRODUCTS = {
    "Milk (1 Litre)": 60.00,
    "Curd (500g)": 45.00,
    "Paneer (200g)": 80.00,
    "Ghee (200ml)": 150.00,
    "Butter (100g)": 55.00,
    "Lassi (200ml)": 30.00,
    "Yogurt (100g)": 25.00,
    "Cream (250ml)": 70.00,
    "Cheese Slice (100g)": 75.00,
    "Flavored Milk (200ml)": 35.00
}

# --- Database Models ---
class DairyEntry(db.Model):
    __tablename__ = 'dairy_entry'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today())
    m_name = db.Column(db.String(100), nullable=False)
    item = db.Column(db.String(100), nullable=False) # This will still store the item name as string
    weight = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    paid = db.Column(db.Float, nullable=False)
    due = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DairyEntry {self.date} - {self.m_name} - {self.item} - Due: {self.due}>"

# --- WTForms ---
class AddDairyEntryForm(FlaskForm):
    date = DateField('Date (YYYY-MM-DD)', format='%Y-%m-%d', default=date.today, validators=[DataRequired()])
    m_name = StringField('Merchant Name', validators=[DataRequired(), Length(min=2, max=100)])
    
    # Changed 'item' from StringField to SelectField
    item = SelectField('Item Name', validators=[DataRequired()]) 
    
    weight = FloatField('Weight', validators=[DataRequired(), NumberRange(min=0.01)])
    unit = StringField('Unit (e.g., kg, pcs)', validators=[DataRequired(), Length(max=50)])
    price_per_unit = FloatField('Price Per Unit', validators=[DataRequired(), NumberRange(min=0)])
    paid = FloatField('Amount Paid (for this entry)', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Add Dairy Entry')

    def __init__(self, *args, **kwargs):
        super(AddDairyEntryForm, self).__init__(*args, **kwargs)
        # Populate choices for item field from DAIRY_PRODUCTS
        # Use (value, label) format for choices
        self.item.choices = [('', 'Select an item')] + [(item_name, item_name) for item_name in DAIRY_PRODUCTS.keys()]

class DairyDailyReportForm(FlaskForm):
    report_date = DateField('Report Date (YYYY-MM-DD)', format='%Y-%m-%d', default=date.today, validators=[DataRequired()])
    total_cash_income = FloatField('Total Cash Income for the Day (from all sources)', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Generate Dairy Daily Report')


# --- Helper Functions ---
def get_previous_dairy_due(current_date, m_name, item):
    previous_date = current_date - timedelta(days=1)
    prev_entry = DairyEntry.query.filter(
        DairyEntry.date == previous_date,
        DairyEntry.m_name == m_name,
        DairyEntry.item == item
    ).order_by(DairyEntry.created_at.desc()).first()

    return prev_entry.due if prev_entry else 0.0

# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html', current_view='home')

@app.route('/add_dairy_entry', methods=['GET', 'POST'])
def add_dairy_entry():
    form = AddDairyEntryForm()
    if form.validate_on_submit():
        entry_date = form.date.data
        m_name = form.m_name.data
        item = form.item.data # This will now be the selected item name from dropdown
        weight = form.weight.data
        unit = form.unit.data
        price_per_unit = form.price_per_unit.data
        paid = form.paid.data

        cost = price_per_unit * weight
        previous_due = get_previous_dairy_due(entry_date, m_name, item)
        current_due = (previous_due + cost) - paid

        new_dairy_entry = DairyEntry(
            date=entry_date,
            m_name=m_name,
            item=item,
            weight=weight,
            unit=unit,
            price_per_unit=price_per_unit,
            cost=cost,
            paid=paid,
            due=current_due
        )
        db.session.add(new_dairy_entry)
        db.session.commit()
        flash('Dairy entry added successfully!', 'success')
        return redirect(url_for('add_dairy_entry'))
    
    # Pass DAIRY_PRODUCTS dictionary to the template for JavaScript lookup
    return render_template('index.html', current_view='add_dairy_entry', form=form, dairy_products=DAIRY_PRODUCTS)

@app.route('/dairy_entries')
def dairy_entries():
    entries_list = DairyEntry.query.order_by(DairyEntry.date.desc(), DairyEntry.created_at.desc()).all()
    return render_template('index.html', current_view='dairy_entries', entries=entries_list)

@app.route('/dairy_daily_summary', methods=['GET', 'POST'])
def dairy_daily_summary():
    form = DairyDailyReportForm()
    report_data = None

    if form.validate_on_submit():
        report_date = form.report_date.data
        total_cash_income = form.total_cash_income.data

        daily_dairy_entries = DairyEntry.query.filter_by(date=report_date).all()

        if not daily_dairy_entries:
            flash(f'No Dairy entries found for {report_date.strftime("%Y-%m-%d")}.', 'info')
            return render_template('index.html', current_view='dairy_daily_summary', form=form)

        total_cost_dairy = sum(entry.cost for entry in daily_dairy_entries)
        total_paid_dairy = sum(entry.paid for entry in daily_dairy_entries)
        profit_loss = total_cash_income - total_cost_dairy

        unique_dues_query = db.session.query(
            DairyEntry.m_name,
            DairyEntry.item,
            func.max(DairyEntry.created_at).label('latest_created_at')
        ).filter(DairyEntry.date == report_date).group_by(DairyEntry.m_name, DairyEntry.item).subquery()

        latest_dues_for_day = db.session.query(func.sum(DairyEntry.due)).join(
            unique_dues_query,
            (DairyEntry.m_name == unique_dues_query.c.m_name) &
            (DairyEntry.item == unique_dues_query.c.item) &
            (DairyEntry.created_at == unique_dues_query.c.latest_created_at)
        ).scalar() or 0.0

        report_data = {
            'date': report_date.strftime('%Y-%m-%d'),
            'total_cost_dairy': total_cost_dairy,
            'total_paid_dairy': total_paid_dairy,
            'total_cash_income': total_cash_income,
            'profit_loss': profit_loss,
            'total_dues_today': latest_dues_for_day
        }
        flash(f'Dairy daily summary generated for {report_date.strftime("%Y-%m-%d")}.', 'success')

    return render_template('index.html', current_view='dairy_daily_summary', form=form, report_data=report_data)

@app.route('/clear_dues', methods=['GET', 'POST'])
def clear_dues():
    # Query users with dues > 0
    users_with_dues = db.session.query(
        DairyEntry.m_name,
        db.func.sum(DairyEntry.due).label('total_due')
    ).group_by(DairyEntry.m_name).having(db.func.sum(DairyEntry.due) > 0).all()

    if request.method == 'POST':
        m_name = request.form['m_name']
        amount_paid = float(request.form['amount_paid'])

        # Get all entries for this user with dues, ordered oldest first
        entries = DairyEntry.query.filter_by(m_name=m_name).filter(DairyEntry.due > 0).order_by(DairyEntry.date).all()
        remaining = amount_paid
        for entry in entries:
            if remaining <= 0:
                break
            pay = min(entry.due, remaining)
            entry.paid += pay
            entry.due -= pay
            remaining -= pay
        db.session.commit()
        flash(f"{m_name}'s dues updated!", 'success')
        return redirect(url_for('clear_dues'))

    return render_template('clear_dues.html', users_with_dues=users_with_dues)

# --- Database Initialization ---
@app.before_request
def create_tables_if_not_exists():
    if not hasattr(app, '_database_initialized'):
        with app.app_context():
            db.create_all()
            app._database_initialized = True

# --- Run the Application ---
if __name__ == '__main__':
    with app.app_context():
        create_tables_if_not_exists()
    app.run(debug=True)