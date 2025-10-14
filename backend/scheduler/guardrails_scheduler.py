"""
Guardrails Scheduler for Multi-Armed Bandit Experiments

Implements scheduled guardrail checks and automatic rollback logic.
Runs guardrail checks every 5 minutes and performs automatic rollback
if multiple guardrails fail or critical guardrails are breached.

Features:
- Scheduled guardrail checks every 5 minutes
- Automatic rollback on guardrail failures
- Alert notifications via logging, email, or Slack
- Decision logging for audit trail
- Configurable thresholds and rollback triggers

Usage:
    from backend.scheduler import setup_guardrails_scheduler
    setup_guardrails_scheduler(scheduler)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from ..database import SessionLocal
from ..models import Experiment
from .guardrails import GuardrailsEngine, GuardrailStatus

logger = logging.getLogger(__name__)

class GuardrailsScheduler:
    """Scheduler for guardrail checks and automatic rollback"""
    
    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self.guardrails_engine = GuardrailsEngine(self.db)
        self.rollback_history = {}  # Track rollback attempts per experiment
        
        # Configuration
        self.check_interval_minutes = 5
        self.rollback_cooldown_hours = 1  # Prevent multiple rollbacks
        self.max_rollback_attempts = 3  # Max rollbacks per experiment
        
        # Alert configuration
        self.alerts_enabled = True
        self.alert_channels = ['logging', 'email', 'slack']  # Configure as needed
    
    def check_all_active_experiments(self):
        """Check guardrails for all active experiments"""
        logger.info("Starting guardrail check for all active experiments")
        
        # Get all active experiments
        active_experiments = self.db.query(Experiment).filter(
            Experiment.end_at.is_(None)  # No end date means active
        ).all()
        
        if not active_experiments:
            logger.info("No active experiments found")
            return
        
        logger.info(f"Found {len(active_experiments)} active experiments")
        
        # Check each experiment
        for experiment in active_experiments:
            try:
                self._check_experiment_guardrails(experiment.id)
            except Exception as e:
                logger.error(f"Failed to check guardrails for experiment {experiment.id}: {e}")
        
        logger.info("Guardrail check complete for all experiments")
    
    def _check_experiment_guardrails(self, experiment_id: str):
        """Check guardrails for a specific experiment"""
        logger.debug(f"Checking guardrails for experiment {experiment_id}")
        
        # Check if we're in rollback cooldown
        if self._is_in_rollback_cooldown(experiment_id):
            logger.info(f"Experiment {experiment_id} is in rollback cooldown, skipping check")
            return
        
        # Run guardrail checks
        summary = self.guardrails_engine.check_guardrails(experiment_id)
        
        # Log the check result
        self._log_guardrail_check(summary)
        
        # Handle rollback if needed
        if summary.should_rollback:
            self._handle_rollback(experiment_id, summary)
        else:
            # Send alerts for warnings
            self._send_alerts_if_needed(summary)
    
    def _is_in_rollback_cooldown(self, experiment_id: str) -> bool:
        """Check if experiment is in rollback cooldown period"""
        if experiment_id not in self.rollback_history:
            return False
        
        last_rollback = self.rollback_history[experiment_id].get('last_rollback')
        if not last_rollback:
            return False
        
        cooldown_end = last_rollback + timedelta(hours=self.rollback_cooldown_hours)
        return datetime.utcnow() < cooldown_end
    
    def _handle_rollback(self, experiment_id: str, summary: Any):
        """Handle automatic rollback for an experiment"""
        logger.warning(f"Triggering automatic rollback for experiment {experiment_id}")
        
        # Check rollback attempt limit
        if self._has_exceeded_rollback_limit(experiment_id):
            logger.error(f"Experiment {experiment_id} has exceeded rollback limit, manual intervention required")
            self._send_critical_alert(experiment_id, "Rollback limit exceeded")
            return
        
        # Perform rollback
        success = self.guardrails_engine.rollback_experiment(experiment_id)
        
        if success:
            # Update rollback history
            self._update_rollback_history(experiment_id, success=True)
            
            # Log the rollback
            self._log_rollback(experiment_id, summary, success=True)
            
            # Send rollback notification
            self._send_rollback_notification(experiment_id, summary, success=True)
            
            logger.info(f"Successfully rolled back experiment {experiment_id}")
        else:
            # Update rollback history
            self._update_rollback_history(experiment_id, success=False)
            
            # Log the failed rollback
            self._log_rollback(experiment_id, summary, success=False)
            
            # Send failure notification
            self._send_rollback_notification(experiment_id, summary, success=False)
            
            logger.error(f"Failed to rollback experiment {experiment_id}")
    
    def _has_exceeded_rollback_limit(self, experiment_id: str) -> bool:
        """Check if experiment has exceeded rollback attempt limit"""
        if experiment_id not in self.rollback_history:
            return False
        
        attempts = self.rollback_history[experiment_id].get('attempts', 0)
        return attempts >= self.max_rollback_attempts
    
    def _update_rollback_history(self, experiment_id: str, success: bool):
        """Update rollback history for an experiment"""
        if experiment_id not in self.rollback_history:
            self.rollback_history[experiment_id] = {
                'attempts': 0,
                'last_rollback': None,
                'last_success': None
            }
        
        self.rollback_history[experiment_id]['attempts'] += 1
        self.rollback_history[experiment_id]['last_rollback'] = datetime.utcnow()
        
        if success:
            self.rollback_history[experiment_id]['last_success'] = datetime.utcnow()
    
    def _log_guardrail_check(self, summary: Any):
        """Log guardrail check results"""
        logger.info(f"Guardrail check for experiment {summary.experiment_id}: {summary.overall_status.value}")
        
        for guardrail in summary.guardrails:
            logger.info(f"  {guardrail.name}: {guardrail.status.value} - {guardrail.message}")
    
    def _log_rollback(self, experiment_id: str, summary: Any, success: bool):
        """Log rollback attempt"""
        status = "SUCCESS" if success else "FAILED"
        logger.warning(f"ROLLBACK {status} for experiment {experiment_id}")
        
        # Log guardrail details
        for guardrail in summary.guardrails:
            if guardrail.status == GuardrailStatus.FAIL:
                logger.warning(f"  Failed guardrail: {guardrail.name} - {guardrail.message}")
    
    def _send_alerts_if_needed(self, summary: Any):
        """Send alerts for guardrail warnings"""
        if not self.alerts_enabled:
            return
        
        # Check if any guardrails are in warning state
        warnings = [g for g in summary.guardrails if g.status == GuardrailStatus.WARNING]
        
        if warnings:
            self._send_warning_alert(summary.experiment_id, warnings)
    
    def _send_warning_alert(self, experiment_id: str, warnings: List[Any]):
        """Send warning alert for guardrail warnings"""
        message = f"Guardrail warnings for experiment {experiment_id}:\n"
        for warning in warnings:
            message += f"- {warning.name}: {warning.message}\n"
        
        logger.warning(message)
        
        # Send to configured channels
        for channel in self.alert_channels:
            if channel == 'logging':
                logger.warning(f"GUARDRAIL WARNING: {message}")
            elif channel == 'email':
                self._send_email_alert(experiment_id, message)
            elif channel == 'slack':
                self._send_slack_alert(experiment_id, message)
    
    def _send_critical_alert(self, experiment_id: str, message: str):
        """Send critical alert for serious issues"""
        full_message = f"CRITICAL: {message} for experiment {experiment_id}"
        
        logger.error(full_message)
        
        # Send to configured channels
        for channel in self.alert_channels:
            if channel == 'logging':
                logger.error(f"GUARDRAIL CRITICAL: {full_message}")
            elif channel == 'email':
                self._send_email_alert(experiment_id, full_message, critical=True)
            elif channel == 'slack':
                self._send_slack_alert(experiment_id, full_message, critical=True)
    
    def _send_rollback_notification(self, experiment_id: str, summary: Any, success: bool):
        """Send rollback notification"""
        status = "SUCCESSFUL" if success else "FAILED"
        message = f"ROLLBACK {status} for experiment {experiment_id}\n"
        
        if success:
            message += "Experiment has been automatically rolled back to control policy.\n"
        else:
            message += "Automatic rollback failed. Manual intervention required.\n"
        
        # Add guardrail details
        message += "Failed guardrails:\n"
        for guardrail in summary.guardrails:
            if guardrail.status == GuardrailStatus.FAIL:
                message += f"- {guardrail.name}: {guardrail.message}\n"
        
        logger.warning(f"ROLLBACK NOTIFICATION: {message}")
        
        # Send to configured channels
        for channel in self.alert_channels:
            if channel == 'logging':
                logger.warning(f"GUARDRAIL ROLLBACK: {message}")
            elif channel == 'email':
                self._send_email_alert(experiment_id, message, critical=True)
            elif channel == 'slack':
                self._send_slack_alert(experiment_id, message, critical=True)
    
    def _send_email_alert(self, experiment_id: str, message: str, critical: bool = False):
        """Send email alert (placeholder implementation)"""
        # In a real system, this would integrate with an email service
        # like SendGrid, SES, or SMTP
        logger.info(f"EMAIL ALERT {'(CRITICAL)' if critical else ''}: {message}")
    
    def _send_slack_alert(self, experiment_id: str, message: str, critical: bool = False):
        """Send Slack alert (placeholder implementation)"""
        # In a real system, this would integrate with Slack webhooks
        # or Slack API
        logger.info(f"SLACK ALERT {'(CRITICAL)' if critical else ''}: {message}")
    
    def get_rollback_history(self, experiment_id: str) -> Dict[str, Any]:
        """Get rollback history for an experiment"""
        return self.rollback_history.get(experiment_id, {})
    
    def reset_rollback_history(self, experiment_id: str):
        """Reset rollback history for an experiment"""
        if experiment_id in self.rollback_history:
            del self.rollback_history[experiment_id]
            logger.info(f"Reset rollback history for experiment {experiment_id}")
    
    def update_config(self, config: Dict[str, Any]):
        """Update scheduler configuration"""
        if 'check_interval_minutes' in config:
            self.check_interval_minutes = config['check_interval_minutes']
        
        if 'rollback_cooldown_hours' in config:
            self.rollback_cooldown_hours = config['rollback_cooldown_hours']
        
        if 'max_rollback_attempts' in config:
            self.max_rollback_attempts = config['max_rollback_attempts']
        
        if 'alerts_enabled' in config:
            self.alerts_enabled = config['alerts_enabled']
        
        if 'alert_channels' in config:
            self.alert_channels = config['alert_channels']
        
        logger.info(f"Updated scheduler configuration: {config}")

# Global scheduler instance
_guardrails_scheduler = None

def get_guardrails_scheduler() -> GuardrailsScheduler:
    """Get the global guardrails scheduler instance"""
    global _guardrails_scheduler
    if _guardrails_scheduler is None:
        _guardrails_scheduler = GuardrailsScheduler()
    return _guardrails_scheduler

def setup_guardrails_scheduler(scheduler):
    """Set up guardrail checks in the main scheduler"""
    logger.info("Setting up guardrails scheduler")
    
    def guardrail_check_job():
        """Job to check guardrails for all active experiments"""
        try:
            guardrails_scheduler = get_guardrails_scheduler()
            guardrails_scheduler.check_all_active_experiments()
        except Exception as e:
            logger.error(f"Guardrail check job failed: {e}")
    
    # Schedule guardrail checks every 5 minutes
    scheduler.add_job(
        guardrail_check_job,
        'interval',
        minutes=5,
        id='guardrail_checks',
        replace_existing=True
    )
    
    logger.info("Guardrails scheduler configured")

def manual_guardrail_check(experiment_id: str) -> Dict[str, Any]:
    """Manually trigger guardrail check for an experiment"""
    guardrails_scheduler = get_guardrails_scheduler()
    guardrails_scheduler._check_experiment_guardrails(experiment_id)
    
    # Return the latest check result
    summary = guardrails_scheduler.guardrails_engine.check_guardrails(experiment_id)
    return summary.to_dict()

def manual_rollback(experiment_id: str) -> bool:
    """Manually trigger rollback for an experiment"""
    guardrails_scheduler = get_guardrails_scheduler()
    return guardrails_scheduler.guardrails_engine.rollback_experiment(experiment_id)
