import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from app import db
from app.models import Payroll, Employee, Department

class PayrollAnalyticsEngine:
    
    @staticmethod
    def get_payroll_dataframe():
        """Extract all payroll data into a pandas DataFrame."""
        query = db.session.query(
            Payroll.payroll_id,
            Payroll.emp_id,
            Payroll.month,
            Payroll.year,
            Payroll.base_salary,
            Payroll.bonus,
            Payroll.overtime_pay,
            Payroll.tax,
            Payroll.deductions,
            Payroll.net_salary,
            Employee.department_id,
            Department.dept_name
        ).join(Employee, Payroll.emp_id == Employee.emp_id)\
         .join(Department, Employee.department_id == Department.dept_id)
        
        # Read SQL query directly into a DataFrame using the SQLAlchemy engine
        df = pd.read_sql(query.statement, db.engine)
        return df

    @staticmethod
    def detect_salary_anomalies(df):
        """
        Detects anomalies using Statistical Standard Deviation.
        An anomaly is defined as a net_salary > mean + 2*std_dev 
        or a massive variance in bonuses.
        """
        if df.empty:
            return []

        # Find the mean and std deviation of the net salary
        mean_salary = df['net_salary'].mean()
        std_salary = df['net_salary'].std()
        
        threshold = mean_salary + (2 * std_salary)
        
        # Filter dataframe for anomalies
        anomalies_df = df[df['net_salary'] > threshold]
        
        anomalies = []
        for _, row in anomalies_df.iterrows():
            emp = Employee.query.get(row['emp_id'])
            anomalies.append({
                'employee_name': emp.name,
                'department': row['dept_name'],
                'date': f"{int(row['month'])}/{int(row['year'])}",
                'net_salary': float(row['net_salary']),
                'bonus': float(row['bonus']),
                'reason': 'Salary > 2 Std Dev from Mean'
            })
            
        return anomalies

    @staticmethod
    def predict_next_month_cost(df):
        """
        Uses Simple Linear Regression to predict the next month's total company payroll cost.
        """
        if df.empty:
            return 0.0

        # Group total cost by month and year
        # Create a time index for regression (e.g., month 1, month 2... month n)
        monthly_costs = df.groupby(['year', 'month'])['net_salary'].sum().reset_index()
        monthly_costs = monthly_costs.sort_values(by=['year', 'month'])
        
        # Create a sequential time feature (X)
        monthly_costs['time_index'] = np.arange(len(monthly_costs))
        
        X = monthly_costs[['time_index']].values
        y = monthly_costs['net_salary'].values

        if len(X) < 2:
            return y[0] if len(y) > 0 else 0.0 # Not enough data to predict

        model = LinearRegression()
        model.fit(X, y)

        # Predict the next month (index = max + 1)
        next_index = np.array([[len(monthly_costs)]])
        prediction = model.predict(next_index)[0]
        
        return round(float(prediction), 2)

    @staticmethod
    def get_department_cost_distribution(df):
        """Returns data formatted for a Chart.js Pie/Donut Chart."""
        if df.empty:
            return {'labels': [], 'data': []}
            
        # Get the latest month/year in the dataset for accurate current distribution
        latest_year = df['year'].max()
        latest_month = df[df['year'] == latest_year]['month'].max()
        
        latest_df = df[(df['year'] == latest_year) & (df['month'] == latest_month)]
        
        dept_costs = latest_df.groupby('dept_name')['net_salary'].sum().reset_index()
        
        return {
            'labels': dept_costs['dept_name'].tolist(),
            'data': [float(x) for x in dept_costs['net_salary'].tolist()]
        }

    @staticmethod
    def get_monthly_trend(df):
        """Returns the last 12 months total payroll trend for a Line chart."""
        if df.empty:
            return {'labels': [], 'data': []}
            
        monthly_costs = df.groupby(['year', 'month'])['net_salary'].sum().reset_index()
        monthly_costs = monthly_costs.sort_values(by=['year', 'month']).tail(12)
        
        labels = [f"{m}/{y}" for m, y in zip(monthly_costs['month'], monthly_costs['year'])]
        data = [float(x) for x in monthly_costs['net_salary'].tolist()]
        
        return {
            'labels': labels,
            'data': data
        }
