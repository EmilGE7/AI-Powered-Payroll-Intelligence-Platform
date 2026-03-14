from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))

def create_app(config_class=Config):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # Register blueprints here
    from app.routes.main import main_bp
    from app.auth.routes import auth_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    # Initialize APScheduler for Background ML Anomaly Detection Jobs
    from apscheduler.schedulers.background import BackgroundScheduler
    import logging
    
    # Configure basic logging for the scheduler
    logging.basicConfig()
    logging.getLogger('apscheduler').setLevel(logging.INFO)
    
    scheduler = BackgroundScheduler()
    
    def run_anomaly_detection_job():
        with app.app_context():
            from app.analytics.engine import PayrollAnalyticsEngine
            df = PayrollAnalyticsEngine.get_payroll_dataframe()
            if not df.empty:
                print("[BACKGROUND JOB] Running automated salary anomaly detection...")
                anomalies = PayrollAnalyticsEngine.detect_salary_anomalies(df)
                if anomalies:
                    print(f"[BACKGROUND JOB] WARNING: {len(anomalies)} anomalies detected!")
                else:
                    print("[BACKGROUND JOB] System clear. No anomalies found.")

    # Run the job every 24 hours (for demonstration, we will set it to run more frequently or just register it)
    scheduler.add_job(func=run_anomaly_detection_job, trigger="interval", hours=24, id='anomaly_detection_job')
    
    # Only start if not running in the werkzeug reloader sub-process to prevent duplicate jobs
    import os
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        scheduler.start()

    return app

