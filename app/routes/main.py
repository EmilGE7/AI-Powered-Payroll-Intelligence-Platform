import json
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models import Employee, Payroll, Department
from app.analytics.engine import PayrollAnalyticsEngine
from app import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Gather high level metrics
    total_employees = Employee.query.filter_by(is_active=True).count()
    
    # Machine Learning and Analytics Pipeline
    df = PayrollAnalyticsEngine.get_payroll_dataframe()
    
    next_month_cost = PayrollAnalyticsEngine.predict_next_month_cost(df)
    anomalies = PayrollAnalyticsEngine.detect_salary_anomalies(df)
    dept_costs = PayrollAnalyticsEngine.get_department_cost_distribution(df)
    trend = PayrollAnalyticsEngine.get_monthly_trend(df)

    latest_payroll_count = 0
    if not df.empty:
        latest_year = df['year'].max()
        latest_month = df[df['year'] == latest_year]['month'].max()
        latest_payroll_count = len(df[(df['year'] == latest_year) & (df['month'] == latest_month)])

    return render_template('dashboard.html', 
                         title='Analytics Dashboard',
                         total_employees=total_employees,
                         payroll_count=latest_payroll_count,
                         prediction=next_month_cost,
                         anomalies=anomalies,
                         dept_costs=json.dumps(dept_costs),
                         trend=json.dumps(trend))

@main_bp.route('/employees')
@login_required
def employees():
    emps = Employee.query.filter_by(is_active=True).all()
    return render_template('employees.html', title='Manage Employees', employees=emps)

@main_bp.route('/payroll_processing')
@login_required
def payroll_processing():
    return render_template('payroll_processing.html', title='Process Payroll')
