import random
from datetime import date, timedelta
from faker import Faker
from app import create_app, db
from app.models import User, Department, Employee, Attendance, Payroll

fake = Faker()
app = create_app()

def seed_database():
    with app.app_context():
        # Clear existing
        db.drop_all()
        db.create_all()

        print("Creating admin user...")
        admin = User(username='admin', email='admin@payroll.ai', role='Admin')
        admin.set_password('admin')
        db.session.add(admin)

        print("Creating departments...")
        depts = ['Engineering', 'Marketing', 'Sales', 'HR', 'Finance', 'Operations']
        db_depts = []
        for d_name in depts:
            dept = Department(dept_name=d_name)
            db.session.add(dept)
            db_depts.append(dept)
        
        db.session.commit()

        print("Generating 100 fake employees...")
        employees = []
        designations = ['Junior Analyst', 'Senior Analyst', 'Manager', 'Director', 'VP', 'Executive']
        
        for _ in range(100):
            emp = Employee(
                name=fake.name(),
                email=fake.unique.company_email(),
                department=random.choice(db_depts),
                designation=random.choice(designations),
                join_date=fake.date_between(start_date='-5y', end_date='today'),
                base_salary=round(random.uniform(40000, 150000), 2)
            )
            db.session.add(emp)
            db.session.flush() # Get the auto-increment emp_id
            
            # Create user account
            username = emp.email.split('@')[0]
            user_acct = User(username=username, email=emp.email, role='Employee', emp_id=emp.emp_id)
            user_acct.set_password('password123')
            db.session.add(user_acct)
            
            employees.append(emp)
        
        db.session.commit()

        print("Generating historical attendance and payroll for the last 12 months...")
        current_year = 2026
        # Let's say we are in March 2026. Generate Jan 2025 -> Feb 2026 (14 months)
        months_to_gen = []
        for y in [2025, 2026]:
            for m in range(1, 13):
                if y == 2026 and m > 2:
                    continue # Stop at Feb 2026
                months_to_gen.append((m, y))

        for month, year in months_to_gen:
            for emp in employees:
                # 1. Generate Attendance
                working_days = random.randint(18, 22)
                leave_days = 22 - working_days
                # Simulate anomaly: 2% chance of crazy overtime
                overtime_hours = random.randint(0, 5)
                if random.random() < 0.02:
                    overtime_hours = random.randint(20, 50) # Anomaly!

                att = Attendance(
                    emp_id=emp.emp_id,
                    month=month,
                    year=year,
                    working_days=working_days,
                    leave_days=leave_days,
                    overtime_hours=overtime_hours
                )
                db.session.add(att)

                # 2. Process Payroll for that month
                monthly_base = float(emp.base_salary) / 12
                
                # Hourly rate approx
                hourly_rate = monthly_base / (20 * 8) 
                overtime_pay = overtime_hours * (hourly_rate * 1.5)
                
                # Simulate Anomaly: 1% chance of massive bonus
                bonus = 0.0
                if month == 12: # December bonus
                    bonus = monthly_base * random.uniform(0.1, 0.5)
                if random.random() < 0.01:
                    bonus = monthly_base * random.uniform(1.0, 3.0) # Massive anomaly!

                # Basic tax calc (e.g. 20% flat rate)
                taxable = monthly_base + bonus + overtime_pay
                tax = taxable * 0.20
                deductions = leave_days * (monthly_base / 22) # Unpaid leave deduction calc
                
                net = taxable - tax - deductions

                payroll = Payroll(
                    emp_id=emp.emp_id,
                    month=month,
                    year=year,
                    base_salary=round(monthly_base, 2),
                    bonus=round(bonus, 2),
                    overtime_pay=round(overtime_pay, 2),
                    tax=round(tax, 2),
                    deductions=round(deductions, 2),
                    net_salary=round(net, 2),
                    status='Approved'
                )
                db.session.add(payroll)

        # Commit all attendance and payroll batches
        print("Committing massive transaction...")
        db.session.commit()
        print("Success! Database seeded completely with anomalies prepared for ML.")

if __name__ == '__main__':
    seed_database()
