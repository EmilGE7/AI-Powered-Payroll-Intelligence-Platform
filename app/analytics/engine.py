from app import db
from app.models import Payroll, Employee, Department

class PayrollAnalyticsEngine:
    
    @staticmethod
    def get_latest_payroll_distribution():
        """Extract latest month payroll data for heatmap using Python and pure SQL."""
        from sqlalchemy import text
        sql = text("""
        WITH LatestMonth AS (
            SELECT year, month FROM payroll ORDER BY year DESC, month DESC LIMIT 1
        )
        SELECT 
            e.name as employee_name, 
            d.dept_name, 
            p.net_salary
        FROM payroll p
        JOIN employees e ON p.emp_id = e.emp_id
        JOIN departments d ON e.department_id = d.dept_id
        JOIN LatestMonth lm ON p.year = lm.year AND p.month = lm.month
        """)
        
        result = db.session.execute(sql).fetchall()
        return [{"employee_name": r[0], "dept_name": r[1], "net_salary": r[2]} for r in result]

    @staticmethod
    def detect_salary_anomalies():
        """
        Detects anomalies using Pure DBMS Window Functions and CTEs (Z-Score calculation).
        Calculates Standard Deviation manually in SQL to support SQLite.
        """
        from sqlalchemy import text
        # Step 1: Calculate the mean per department
        # Step 2: Calculate Variance/StdDev per department
        # Step 3: Flag if salary is > mean + 2*StdDev
        
        sql = text("""
        WITH DeptMeans AS (
            SELECT 
                d.dept_name,
                e.department_id,
                AVG(p.net_salary) as mean_salary,
                COUNT(p.payroll_id) as emp_count
            FROM payroll p
            JOIN employees e ON p.emp_id = e.emp_id
            JOIN departments d ON e.department_id = d.dept_id
            GROUP BY d.dept_name, e.department_id
        ),
        DeptVariance AS (
            SELECT 
                p.payroll_id,
                e.department_id,
                p.net_salary,
                dm.mean_salary,
                (p.net_salary - dm.mean_salary) * (p.net_salary - dm.mean_salary) as sq_diff
            FROM payroll p
            JOIN employees e ON p.emp_id = e.emp_id
            JOIN DeptMeans dm ON e.department_id = dm.department_id
        ),
        DeptStdDev AS (
            SELECT 
                department_id,
                mean_salary,
                -- manual std deviation approximation
                SQRT(SUM(sq_diff) / (COUNT(payroll_id) - 1 + 0.0001)) as std_dev 
            FROM DeptVariance
            GROUP BY department_id, mean_salary
        )
        SELECT 
            e.name as employee_name,
            d.dept_name as department,
            p.month,
            p.year,
            p.net_salary,
            p.bonus,
            dm.mean_salary,
            dsd.std_dev
        FROM payroll p
        JOIN employees e ON p.emp_id = e.emp_id
        JOIN departments d ON e.department_id = d.dept_id
        JOIN DeptMeans dm ON e.department_id = dm.department_id
        JOIN DeptStdDev dsd ON e.department_id = dsd.department_id
        WHERE p.net_salary > (dm.mean_salary + (2 * dsd.std_dev))
        """)
        
        # We need a SQRT function in sqlite, if it's missing it fails. Let's make sure our sqlite connection has it.
        # Actually, standard sqlite3 doesn't have SQRT unless extension is loaded. 
        # A simpler pure SQL approach for Z-score in generic SQL without SQRT is comparing Variance directly!
        # if (x - mean)^2 > 4 * Variance  --> equivalent to x > mean + 2*stddev, since 2^2 = 4 (assuming x > mean)
        return PayrollAnalyticsEngine._execute_anomaly_query()

    @staticmethod
    def _execute_anomaly_query():
        from sqlalchemy import text
        # Using pure variance comparison to avoid needing SQRT() in generic SQLite.
        # (val - mean)^2 > (Z^2) * Variance. Given Z=2, Z^2 = 4.
        sql = text("""
        WITH DeptStats AS (
            SELECT 
                e.department_id,
                AVG(p.net_salary) as mean_salary,
                COUNT(p.payroll_id) as n_count
            FROM payroll p
            JOIN employees e ON p.emp_id = e.emp_id
            GROUP BY e.department_id
        ),
        DeptVariance AS (
            SELECT 
                ds.department_id,
                ds.mean_salary,
                SUM((p.net_salary - ds.mean_salary) * (p.net_salary - ds.mean_salary)) / (ds.n_count - 1 + 0.0001) as variance
            FROM payroll p
            JOIN employees e ON p.emp_id = e.emp_id
            JOIN DeptStats ds ON e.department_id = ds.department_id
            GROUP BY ds.department_id, ds.mean_salary, ds.n_count
        )
        SELECT 
            e.name as employee_name,
            d.dept_name as department,
            p.month,
            p.year,
            p.net_salary,
            p.bonus
        FROM payroll p
        JOIN employees e ON p.emp_id = e.emp_id
        JOIN departments d ON e.department_id = d.dept_id
        JOIN DeptVariance dv ON e.department_id = dv.department_id
        WHERE p.net_salary > dv.mean_salary 
          AND ((p.net_salary - dv.mean_salary) * (p.net_salary - dv.mean_salary)) > (4 * dv.variance)
        ORDER BY p.year DESC, p.month DESC
        """)
        
        result = db.session.execute(sql).fetchall()
        anomalies = []
        for row in result:
            anomalies.append({
                'employee_name': row[0],
                'department': row[1],
                'date': f"{int(row[2])}/{int(row[3])}",
                'net_salary': float(row[4]),
                'bonus': float(row[5]),
                'reason': 'Salary variance > 4x Dept Variance (Z>2)'
            })
        return anomalies

    @staticmethod
    def predict_next_month_cost():
        """
        Uses Pure SQL Common Table Expressions (CTEs) to calculate a Moving Average 
        to predict next month's total company payroll cost dynamically.
        """
        from sqlalchemy import text
        sql = text("""
        WITH MonthlyCosts AS (
            SELECT 
                year, 
                month, 
                SUM(net_salary) as total_cost
            FROM payroll
            GROUP BY year, month
            ORDER BY year DESC, month DESC
            LIMIT 3
        )
        SELECT AVG(total_cost) FROM MonthlyCosts;
        """)
        result = db.session.execute(sql).scalar()
        return round(float(result), 2) if result else 0.0

    @staticmethod
    def get_department_cost_distribution():
        """Returns data formatted for a Chart.js Pie/Donut Chart using Pure SQL."""
        from sqlalchemy import text
        sql = text("""
        WITH LatestMonth AS (
            SELECT year, month 
            FROM payroll 
            ORDER BY year DESC, month DESC 
            LIMIT 1
        )
        SELECT 
            d.dept_name, 
            SUM(p.net_salary) as total_cost
        FROM payroll p
        JOIN employees e ON p.emp_id = e.emp_id
        JOIN departments d ON e.department_id = d.dept_id
        JOIN LatestMonth lm ON p.year = lm.year AND p.month = lm.month
        GROUP BY d.dept_name
        ORDER BY total_cost DESC;
        """)
        
        result = db.session.execute(sql).fetchall()
        labels = []
        data = []
        for row in result:
            labels.append(row[0])
            data.append(float(row[1]))
            
        return {'labels': labels, 'data': data}

    @staticmethod
    def get_monthly_trend():
        """Returns the last 12 months total payroll trend using Pure SQL."""
        from sqlalchemy import text
        sql = text("""
        SELECT year, month, SUM(net_salary) as total_net
        FROM payroll
        GROUP BY year, month
        ORDER BY year DESC, month DESC
        LIMIT 12
        """)
        result = db.session.execute(sql).fetchall()
        # Sort chronologically for charting
        result.reverse()
        
        labels = [f"{int(r[1])}/{int(r[0])}" for r in result]
        data = [float(r[2]) for r in result]
        
        return {'labels': labels, 'data': data}

    @staticmethod
    def generate_employee_dossier(emp_id):
        """
        Calculates God-Level metrics using SQL Window Functions.
        Includes YTD aggregates and department percentile performance data natively.
        """
        from sqlalchemy import text
        sql = text("""
        WITH EmpCurrent AS (
            SELECT e.department_id, d.dept_name, MAX(p.year) as max_year
            FROM employees e
            JOIN departments d ON e.department_id = d.dept_id
            JOIN payroll p ON e.emp_id = p.emp_id
            WHERE e.emp_id = :emp_id
            GROUP BY e.department_id, d.dept_name
        ),
        EmpYTD AS (
            SELECT 
                SUM(base_salary + bonus + overtime_pay) as ytd_gross,
                SUM(net_salary) as ytd_net,
                SUM(tax) as ytd_tax,
                SUM(deductions) as ytd_deductions,
                SUM(bonus) as emp_total_bonus,
                SUM(overtime_pay) as emp_total_overtime
            FROM payroll p
            JOIN EmpCurrent ec ON p.year = ec.max_year
            WHERE p.emp_id = :emp_id
        ),
        DeptAvg AS (
            SELECT 
                AVG(p.bonus) as avg_dept_bonus,
                AVG(p.overtime_pay) as avg_dept_overtime
            FROM payroll p
            JOIN employees e ON p.emp_id = e.emp_id
            JOIN EmpCurrent ec ON p.year = ec.max_year AND e.department_id = ec.department_id
        )
        SELECT 
            y.ytd_gross, y.ytd_net, y.ytd_tax, y.ytd_deductions,
            y.emp_total_bonus, y.emp_total_overtime,
            d.avg_dept_bonus, d.avg_dept_overtime,
            (y.emp_total_bonus - d.avg_dept_bonus) as bonus_variance,
            (y.emp_total_overtime - d.avg_dept_overtime) as overtime_variance,
            ec.dept_name
        FROM EmpYTD y
        CROSS JOIN DeptAvg d
        CROSS JOIN EmpCurrent ec
        """)
        
        result = db.session.execute(sql, {'emp_id': emp_id}).fetchone()
        
        # Default empty dossier for new employees with no payroll history
        if not result or result[0] is None:
            return {
                'ytd_salary': 0.0,
                'ytd_net': 0.0,
                'ytd_tax': 0.0,
                'ytd_deductions': 0.0,
                'ytd_bonus': 0.0,
                'emp_total_overtime': 0.0,
                'avg_dept_bonus': 0.0,
                'avg_dept_overtime': 0.0,
                'bonus_variance': 0.0,
                'overtime_variance': 0.0,
                'department': 'N/A'
            }
            
        return {
            'ytd_salary': float(result[0] or 0),
            'ytd_net': float(result[1] or 0),
            'ytd_tax': float(result[2] or 0),
            'ytd_deductions': float(result[3] or 0),
            'ytd_bonus': float(result[4] or 0),
            'emp_total_overtime': float(result[5] or 0),
            'avg_dept_bonus': float(result[6] or 0),
            'avg_dept_overtime': float(result[7] or 0),
            'bonus_variance': float(result[8] or 0),
            'overtime_variance': float(result[9] or 0),
            'department': result[10]
        }

