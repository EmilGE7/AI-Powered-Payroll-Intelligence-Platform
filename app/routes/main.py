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
    
    # Pure DBMS Analytics Pipeline
    next_month_cost = PayrollAnalyticsEngine.predict_next_month_cost()
    anomalies = PayrollAnalyticsEngine.detect_salary_anomalies()
    dept_costs = PayrollAnalyticsEngine.get_department_cost_distribution()
    trend = PayrollAnalyticsEngine.get_monthly_trend()

    latest_dist = PayrollAnalyticsEngine.get_latest_payroll_distribution()
    latest_payroll_count = len(latest_dist)
    heatmap_json = "{}"
    if latest_dist:
        unique_depts = list(set([row['dept_name'] for row in latest_dist]))
        dept_mapping = {name: i for i, name in enumerate(unique_depts)}
        heatmap_data = []
        for row in latest_dist:
            heatmap_data.append({
                'x': float(dept_mapping[row['dept_name']]),
                'y': float(row['net_salary']),
                'name': row['employee_name'],
                'dept': row['dept_name']
            })
        heatmap_json = json.dumps({'data': heatmap_data, 'labels': unique_depts})

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
    import csv
    import io
    from sqlalchemy import text
    
    sql = text("""
    SELECT 
        p.payroll_id, 
        e.name as employee_name, 
        d.dept_name, 
        p.month, 
        p.year, 
        p.base_salary, 
        p.bonus, 
        p.overtime_pay, 
        p.tax, 
        p.deductions, 
        p.net_salary
    FROM payroll p
    JOIN employees e ON p.emp_id = e.emp_id
    JOIN departments d ON e.department_id = d.dept_id
    ORDER BY p.year DESC, p.month DESC
    """)
    result = db.session.execute(sql)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(result.keys())
    for row in result:
        writer.writerow(row)
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=payroll_export.csv"}
    )

@main_bp.route('/employees')
@login_required
def employees():
    emps = Employee.query.filter_by(is_active=True).all()
    depts = Department.query.all()
    return render_template('employees.html', title='Manage Employees', employees=emps, depts=depts)

@main_bp.route('/employee/<int:emp_id>')
@login_required
def employee_details(emp_id):
    if current_user.role not in ['Admin', 'HR', 'Finance']:
        flash('Access Denied.', 'danger')
        return redirect(url_for('main.dashboard'))
        
    emp = Employee.query.get_or_404(emp_id)
    dept = Department.query.get(emp.department_id)
    dossier = PayrollAnalyticsEngine.generate_employee_dossier(emp_id)
    
    payrolls = Payroll.query.filter_by(emp_id=emp_id).order_by(Payroll.year.desc(), Payroll.month.desc()).all()
    
    return render_template('employee_details.html', title=f"Employee: {emp.name}", employee=emp, department=dept, dossier=dossier, payrolls=payrolls)

@main_bp.route('/employee/<int:emp_id>/adjust', methods=['POST'])
@login_required
def adjust_employee_pay(emp_id):
    if current_user.role not in ['Admin', 'HR', 'Finance']:
        flash('Access Denied.', 'danger')
        return redirect(url_for('main.dashboard'))
        
    emp = Employee.query.get_or_404(emp_id)
    
    new_base = request.form.get('new_base_salary')
    pending_bonus = request.form.get('pending_bonus')
    pending_deduction = request.form.get('pending_deduction')
    
    if new_base:
        emp.base_salary = float(new_base)
    if pending_bonus:
        emp.pending_bonus = float(pending_bonus)
    else:
        emp.pending_bonus = 0.0
        
    if pending_deduction:
        emp.pending_deduction = float(pending_deduction)
    else:
        emp.pending_deduction = 0.0
        
    db.session.commit()
    flash(f"Payment logic updated for {emp.name}.", "success")
    return redirect(url_for('main.employee_details', emp_id=emp_id))

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
        bonus = emp.pending_bonus or 0.0
        applied_deductions = emp.pending_deduction or 0.0

        tax = float(base) * 0.20 # simple tax calculation
        total_deductions = (float(base) * 0.05) + float(applied_deductions)
        net = float(base) + float(bonus) - tax - total_deductions
        
        pr = Payroll(
            emp_id=emp.emp_id,
            month=month,
            year=year,
            base_salary=base,
            bonus=bonus,
            tax=tax,
            deductions=total_deductions,
            net_salary=net,
            status='Pending'
        )
        db.session.add(pr)

        # Reset pending adjustments after applying them
        emp.pending_bonus = 0.0
        emp.pending_deduction = 0.0
        
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
        
    # Using God-Level SQL Analytics instead of Pandas
    prediction = PayrollAnalyticsEngine.predict_next_month_cost()
    anomalies = PayrollAnalyticsEngine.detect_salary_anomalies()
    dept_costs = PayrollAnalyticsEngine.get_department_cost_distribution()
    
    total_employees = Employee.query.filter_by(is_active=True).count()
    
    # Extract latest period metadata
    from sqlalchemy import text
    sql = text("SELECT year, month FROM payroll ORDER BY year DESC, month DESC LIMIT 1")
    latest = db.session.execute(sql).fetchone()
    
    if not latest:
        flash("No data available for audit.", "warning")
        return redirect(url_for('main.dashboard'))
    
    latest_year, latest_month = latest[0], latest[1]
    total_latest_cost = sum(dept_costs['data'])
    dept_breakdown = zip(dept_costs['labels'], dept_costs['data'])
    
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
                            dept_breakdown=dept_breakdown,
                            anomalies=anomalies)
                            
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=company_audit_{int(latest_month)}_{int(latest_year)}.pdf'
        return response
        
    flash("Error generating PDF audit.", "danger")
    return redirect(url_for('main.dashboard'))

