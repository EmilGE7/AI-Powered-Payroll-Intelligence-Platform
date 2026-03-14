from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='HR') # Admin, HR, Finance, Employee
    emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'), nullable=True)

    employee = db.relationship('Employee', backref='user_account', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Department(db.Model):
    __tablename__ = 'departments'
    dept_id = db.Column(db.Integer, primary_key=True)
    dept_name = db.Column(db.String(100), unique=True)
    
    # Relationships
    employees = db.relationship('Employee', backref='department', lazy='dynamic')

class Employee(db.Model):
    __tablename__ = 'employees'
    emp_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.dept_id'))
    designation = db.Column(db.String(50))
    join_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True) # Soft delete
    
    # Base Salary configuration for the employee
    base_salary = db.Column(db.Numeric(10, 2))
    
    # Scheduled adjustments (resets to 0 after payroll execution)
    pending_bonus = db.Column(db.Numeric(10, 2), default=0.0)
    pending_deduction = db.Column(db.Numeric(10, 2), default=0.0)

    # Relationships
    attendance_records = db.relationship('Attendance', backref='employee', lazy='dynamic')
    payroll_records = db.relationship('Payroll', backref='employee', lazy='dynamic')

class Attendance(db.Model):
    __tablename__ = 'attendance'
    attendance_id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'))
    month = db.Column(db.Integer) # 1-12
    year = db.Column(db.Integer)
    working_days = db.Column(db.Integer, default=0)
    overtime_hours = db.Column(db.Integer, default=0)
    leave_days = db.Column(db.Integer, default=0)

class Payroll(db.Model):
    __tablename__ = 'payroll'
    payroll_id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'))
    month = db.Column(db.Integer)
    year = db.Column(db.Integer)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    
    # Financials
    base_salary = db.Column(db.Numeric(10, 2))
    bonus = db.Column(db.Numeric(10, 2), default=0.0)
    overtime_pay = db.Column(db.Numeric(10, 2), default=0.0)
    tax = db.Column(db.Numeric(10, 2), default=0.0)
    deductions = db.Column(db.Numeric(10, 2), default=0.0)
    net_salary = db.Column(db.Numeric(10, 2))
    
    processed_date = db.Column(db.DateTime, default=datetime.utcnow)

class PayrollAudit(db.Model):
    """
    Simulates a database trigger log for salaries.
    In a true DBMS project, this might be handled by actual Postgres triggers,
    but SQLAlchemy events provide a Pythonic equivalent.
    """
    __tablename__ = 'payroll_audit'
    audit_id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(db.Integer, db.ForeignKey('payroll.payroll_id'))
    emp_id = db.Column(db.Integer, db.ForeignKey('employees.emp_id'))
    old_net_salary = db.Column(db.Numeric(10, 2))
    new_net_salary = db.Column(db.Numeric(10, 2))
    change_time = db.Column(db.DateTime, default=datetime.utcnow)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
