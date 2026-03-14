import json
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from app.models import Employee, Payroll, Department
from app.analytics.engine import PayrollAnalyticsEngine
from app import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'Employee':
            return redirect(url_for('main.employee_portal'))
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/employee_portal')
@login_required
def employee_portal():
    if current_user.role != 'Employee':
        return redirect(url_for('main.dashboard'))
        
    emp = current_user.employee
    if not emp:
        flash("No employee record found for this account.", "danger")
        return redirect(url_for('auth.logout'))
        
    from app.models import Payroll, Attendance
    # Get recent payrolls
    payrolls = Payroll.query.filter_by(emp_id=emp.emp_id, status='Approved').order_by(Payroll.year.desc(), Payroll.month.desc()).limit(12).all()
    
    # Get recent attendance
    attendance = Attendance.query.filter_by(emp_id=emp.emp_id).order_by(Attendance.year.desc(), Attendance.month.desc()).limit(12).all()
    
    return render_template('employee_portal.html', title='My Portal', employee=emp, payrolls=payrolls, attendance=attendance)

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
    heatmap_json = "{}"
    if not df.empty:
        latest_year = df['year'].max()
        latest_month = df[df['year'] == latest_year]['month'].max()
        latest_df = df[(df['year'] == latest_year) & (df['month'] == latest_month)]
        latest_payroll_count = len(latest_df)
        
        # Heatmap / Scatter Data
        dept_mapping = {name: i for i, name in enumerate(latest_df['dept_name'].unique())}
        heatmap_data = []
        for _, row in latest_df.iterrows():
            heatmap_data.append({
                'x': float(dept_mapping[row['dept_name']]),
                'y': float(row['net_salary']),
                'name': row['employee_name'],
                'dept': row['dept_name']
            })
        heatmap_json = json.dumps({'data': heatmap_data, 'labels': list(dept_mapping.keys())})

    return render_template('dashboard.html', 
                         title='Analytics Dashboard',
                         total_employees=total_employees,
                         payroll_count=latest_payroll_count,
                         prediction=next_month_cost,
                         anomalies=anomalies,
                         dept_costs=json.dumps(dept_costs),
                         trend=json.dumps(trend),
                         heatmap_json=heatmap_json)

@main_bp.route('/export/csv')
@login_required
def export_csv():
    df = PayrollAnalyticsEngine.get_payroll_dataframe()
    return Response(
        df.to_csv(index=False),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=payroll_export.csv"}
    )

@main_bp.route('/employees')
@login_required
def employees():
    emps = Employee.query.filter_by(is_active=True).all()
    depts = Department.query.all()
    return render_template('employees.html', title='Manage Employees', employees=emps, depts=depts)

@main_bp.route('/employees/add', methods=['POST'])
@login_required
def add_employee():
    name = request.form.get('name')
    email = request.form.get('email')
    dept_id = request.form.get('department')
    designation = request.form.get('designation')
    base_salary = request.form.get('base_salary')
    
    dept = Department.query.get(dept_id)
    emp = Employee(
        name=name,
        email=email,
        department=dept,
        designation=designation,
        join_date=date.today(),
        base_salary=float(base_salary)
    )
    db.session.add(emp)
    db.session.commit()
    flash('Employee added successfully.', 'success')
    return redirect(url_for('main.employees'))

@main_bp.route('/employees/delete/<int:emp_id>', methods=['POST'])
@login_required
def delete_employee(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    emp.is_active = False
    db.session.commit()
    flash(f'{emp.name} has been archived.', 'info')
    return redirect(url_for('main.employees'))

@main_bp.route('/payroll_processing')
@login_required
def payroll_processing():
    return render_template('payroll_processing.html', title='Process Payroll')

@main_bp.route('/payroll_processing/trigger', methods=['POST'])
@login_required
def trigger_payroll():
    if current_user.role not in ['Admin', 'HR']:
        flash('Access Denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    month = int(request.form.get('month'))
    year = int(request.form.get('year'))
    
    existing = Payroll.query.filter_by(month=month, year=year).first()
    if existing:
        flash(f'Payroll for {month}/{year} already exists.', 'warning')
        return redirect(url_for('main.payroll_processing'))
        
    emps = Employee.query.filter_by(is_active=True).all()
    for emp in emps:
        base = emp.base_salary
        tax = float(base) * 0.20 # simple tax calculation
        deductions = float(base) * 0.05
        net = float(base) - tax - deductions
        pr = Payroll(
            emp_id=emp.emp_id,
            month=month,
            year=year,
            base_salary=base,
            tax=tax,
            deductions=deductions,
            net_salary=net,
            status='Pending'
        )
        db.session.add(pr)
    db.session.commit()
    
    flash(f'Payroll Engine generated {len(emps)} slips for {month}/{year}. Sent to Approvals Inbox.', 'success')
    return redirect(url_for('main.payroll_processing'))

@main_bp.route('/approvals')
@login_required
def approvals():
    if current_user.role not in ['Admin', 'Finance', 'HR']:
        flash('Access Denied.', 'danger')
        return redirect(url_for('main.dashboard'))
        
    from sqlalchemy import func
    pending_batches = db.session.query(
        Payroll.month, Payroll.year, func.count(Payroll.payroll_id).label('emp_count'), func.sum(Payroll.net_salary).label('total_net')
    ).filter_by(status='Pending').group_by(Payroll.month, Payroll.year).all()
    
    return render_template('approvals.html', title='Payroll Approvals', batches=pending_batches)

@main_bp.route('/approvals/action/<int:month>/<int:year>', methods=['POST'])
@login_required
def approval_action(month, year):
    if current_user.role not in ['Admin', 'Finance']:
        flash('Access Denied. Only Finance/Admin can approve payrolls.', 'danger')
        return redirect(url_for('main.approvals'))
        
    action = request.form.get('action')
    payrolls = Payroll.query.filter_by(month=month, year=year, status='Pending').all()
    
    new_status = 'Approved' if action == 'approve' else 'Rejected'
    for pr in payrolls:
        pr.status = new_status
        
    db.session.commit()
    flash(f'Payroll batch {month}/{year} has been {new_status}.', 'success')
    return redirect(url_for('main.approvals'))

@main_bp.route('/reports/employee/<int:emp_id>')
@login_required
def generate_employee_report(emp_id):
    # Security Check: Only the employee or Admin/HR can view this report.
    if current_user.role == 'Employee' and current_user.employee.emp_id != emp_id:
        flash("Access Denied. You can only view your own reports.", "danger")
        return redirect(url_for('main.employee_portal'))
        
    emp = Employee.query.get_or_404(emp_id)
    dossier = PayrollAnalyticsEngine.generate_employee_dossier(emp_id)
    
    if not dossier:
        flash("Not enough data to generate an employee dossier.", "warning")
        return redirect(url_for('main.dashboard'))
        
    # Import xhtml2pdf here to avoid circular/initialization blocks
    from xhtml2pdf import pisa
    from io import BytesIO
    from flask import make_response
    
    html = render_template('reports/employee_dossier.html', emp=emp, dossier=dossier, date=date.today().strftime('%B %d, %Y'))
    
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=employee_{emp_id}_dossier.pdf'
        return response
        
    flash("Error generating PDF document.", "danger")
    return redirect(url_for('main.dashboard'))

@main_bp.route('/reports/payslip/<int:payroll_id>')
@login_required
def generate_payslip(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    emp = Employee.query.get_or_404(payroll.emp_id)
    
    # Security Check
    if current_user.role == 'Employee' and current_user.employee.emp_id != emp.emp_id:
        flash("Access Denied. You can only view your own payslips.", "danger")
        return redirect(url_for('main.employee_portal'))
        
    from xhtml2pdf import pisa
    from io import BytesIO
    from flask import make_response
    
    html = render_template('reports/payslip.html', emp=emp, payroll=payroll, month=int(payroll.month), year=int(payroll.year))
    
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=payslip_{int(payroll.month)}_{int(payroll.year)}.pdf'
        return response
        
    flash("Error generating PDF payslip.", "danger")
    return redirect(url_for('main.employee_portal'))

@main_bp.route('/reports/company_audit')
@login_required
def generate_company_audit():
    if current_user.role not in ['Admin', 'HR', 'Finance']:
        flash("Access Denied.", "danger")
        return redirect(url_for('main.dashboard'))
        
    df = PayrollAnalyticsEngine.get_payroll_dataframe()
    if df.empty:
        flash("No data available for audit.", "warning")
        return redirect(url_for('main.dashboard'))
        
    total_employees = Employee.query.filter_by(is_active=True).count()
    prediction = PayrollAnalyticsEngine.predict_next_month_cost(df)
    anomalies = PayrollAnalyticsEngine.detect_salary_anomalies(df)
    
    # Department breakdown
    latest_year = df['year'].max()
    latest_month = df[df['year'] == latest_year]['month'].max()
    latest_df = df[(df['year'] == latest_year) & (df['month'] == latest_month)]
    
    total_latest_cost = float(latest_df['net_salary'].sum())
    dept_costs = latest_df.groupby('dept_name')['net_salary'].sum().reset_index()
    dept_labels = dept_costs['dept_name'].tolist()
    dept_data = [float(x) for x in dept_costs['net_salary'].tolist()]
    
    # Trend
    monthly_costs = df.groupby(['year', 'month'])['net_salary'].sum().reset_index()
    monthly_costs = monthly_costs.sort_values(by=['year', 'month']).tail(12)
    trend_labels = [f"{int(m)}/{int(y)}" for m, y in zip(monthly_costs['month'], monthly_costs['year'])]
    trend_data = [float(x) for x in monthly_costs['net_salary'].tolist()]
    
    from xhtml2pdf import pisa
    from io import BytesIO
    from flask import make_response
    
    html = render_template('reports/company_audit.html', 
                            date=date.today().strftime('%B %d, %Y'),
                            total_employees=total_employees,
                            latest_month=int(latest_month),
                            latest_year=int(latest_year),
                            total_latest_cost=total_latest_cost,
                            prediction=prediction,
                            dept_labels=dept_labels,
                            dept_data=dept_data,
                            anomalies=anomalies,
                            trend_labels=trend_labels,
                            trend_data=trend_data)
                            
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=company_audit_{int(latest_month)}_{int(latest_year)}.pdf'
        return response
        
    flash("Error generating PDF audit.", "danger")
    return redirect(url_for('main.dashboard'))

