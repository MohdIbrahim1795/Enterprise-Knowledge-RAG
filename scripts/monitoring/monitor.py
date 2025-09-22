#!/usr/bin/env python3
"""
RAG Chatbot System Monitoring Script
Monitors health, performance, and alerts on issues
"""

import time
import json
import logging
import argparse
import requests
import psutil
import docker
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    """Health check result"""
    service: str
    status: str  # 'healthy', 'unhealthy', 'degraded'
    response_time: float
    details: Dict[str, Any]
    timestamp: datetime


@dataclass
class Alert:
    """Alert configuration"""
    service: str
    metric: str
    threshold: float
    comparison: str  # 'gt', 'lt', 'eq'
    severity: str  # 'critical', 'warning', 'info'


class RAGMonitor:
    """RAG System Monitor"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.services = config.get('services', {})
        self.alerts = [Alert(**alert) for alert in config.get('alerts', [])]
        self.notification_config = config.get('notifications', {})
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker client not available: {e}")
            self.docker_client = None
    
    def check_service_health(self, service_name: str, service_config: Dict[str, Any]) -> HealthCheck:
        """Check health of a single service"""
        start_time = time.time()
        
        try:
            url = service_config.get('health_url')
            timeout = service_config.get('timeout', 10)
            
            response = requests.get(url, timeout=timeout)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    service_status = data.get('status', 'unknown')
                    
                    if service_status in ['healthy', 'ok']:
                        status = 'healthy'
                    elif service_status == 'degraded':
                        status = 'degraded'
                    else:
                        status = 'unhealthy'
                        
                    details = data
                except json.JSONDecodeError:
                    status = 'healthy' if response.status_code == 200 else 'unhealthy'
                    details = {'raw_response': response.text[:200]}
            else:
                status = 'unhealthy'
                details = {'status_code': response.status_code, 'response': response.text[:200]}
                
        except requests.exceptions.RequestException as e:
            response_time = time.time() - start_time
            status = 'unhealthy'
            details = {'error': str(e)}
        
        return HealthCheck(
            service=service_name,
            status=status,
            response_time=response_time,
            details=details,
            timestamp=datetime.now()
        )
    
    def check_docker_containers(self) -> List[HealthCheck]:
        """Check Docker container health"""
        checks = []
        
        if not self.docker_client:
            return checks
        
        try:
            containers = self.docker_client.containers.list()
            
            for container in containers:
                container_name = container.name
                
                # Skip if not in our service list
                if container_name not in [s.replace('-', '_').replace('_', '-') for s in self.services.keys()]:
                    continue
                
                status = 'healthy' if container.status == 'running' else 'unhealthy'
                
                # Get container stats
                try:
                    stats = container.stats(stream=False)
                    cpu_percent = self._calculate_cpu_percent(stats)
                    memory_usage = stats['memory_stats']['usage'] / (1024 * 1024)  # MB
                    
                    details = {
                        'status': container.status,
                        'cpu_percent': cpu_percent,
                        'memory_mb': memory_usage,
                        'image': container.image.tags[0] if container.image.tags else 'unknown'
                    }
                except Exception as e:
                    details = {'status': container.status, 'stats_error': str(e)}
                
                checks.append(HealthCheck(
                    service=f"docker_{container_name}",
                    status=status,
                    response_time=0.0,
                    details=details,
                    timestamp=datetime.now()
                ))
                
        except Exception as e:
            logger.error(f"Error checking Docker containers: {e}")
        
        return checks
    
    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU percentage from Docker stats"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            if system_delta > 0:
                return (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            return 0.0
        except (KeyError, ZeroDivisionError):
            return 0.0
    
    def check_system_resources(self) -> HealthCheck:
        """Check system resource usage"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Determine status based on thresholds
            status = 'healthy'
            if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
                status = 'unhealthy'
            elif cpu_percent > 70 or memory_percent > 70 or disk_percent > 80:
                status = 'degraded'
            
            details = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'disk_percent': disk_percent,
                'memory_available_gb': memory.available / (1024**3),
                'disk_free_gb': disk.free / (1024**3)
            }
            
        except Exception as e:
            status = 'unhealthy'
            details = {'error': str(e)}
        
        return HealthCheck(
            service='system_resources',
            status=status,
            response_time=0.0,
            details=details,
            timestamp=datetime.now()
        )
    
    def run_performance_test(self) -> HealthCheck:
        """Run performance test on chat endpoint"""
        chat_service = self.services.get('fastapi', {})
        chat_url = chat_service.get('chat_url')
        
        if not chat_url:
            return HealthCheck(
                service='performance_test',
                status='unhealthy',
                response_time=0.0,
                details={'error': 'Chat URL not configured'},
                timestamp=datetime.now()
            )
        
        test_queries = [
            "What is machine learning?",
            "Explain artificial intelligence",
            "How does deep learning work?"
        ]
        
        results = []
        start_time = time.time()
        
        for query in test_queries:
            try:
                query_start = time.time()
                response = requests.post(
                    chat_url,
                    json={"query": query},
                    timeout=30
                )
                query_time = time.time() - query_start
                
                results.append({
                    'query': query,
                    'response_time': query_time,
                    'status_code': response.status_code,
                    'success': response.status_code == 200
                })
                
            except Exception as e:
                results.append({
                    'query': query,
                    'error': str(e),
                    'success': False
                })
        
        total_time = time.time() - start_time
        success_rate = sum(1 for r in results if r.get('success', False)) / len(results)
        avg_response_time = sum(r.get('response_time', 0) for r in results) / len(results)
        
        # Determine status
        if success_rate == 1.0 and avg_response_time < 5.0:
            status = 'healthy'
        elif success_rate >= 0.8 and avg_response_time < 10.0:
            status = 'degraded'
        else:
            status = 'unhealthy'
        
        return HealthCheck(
            service='performance_test',
            status=status,
            response_time=total_time,
            details={
                'success_rate': success_rate,
                'avg_response_time': avg_response_time,
                'total_time': total_time,
                'results': results
            },
            timestamp=datetime.now()
        )
    
    def evaluate_alerts(self, health_checks: List[HealthCheck]) -> List[Dict[str, Any]]:
        """Evaluate alerts based on health check results"""
        triggered_alerts = []
        
        for alert in self.alerts:
            for check in health_checks:
                if check.service != alert.service:
                    continue
                
                # Get metric value
                metric_value = None
                if alert.metric == 'response_time':
                    metric_value = check.response_time
                elif alert.metric == 'status':
                    metric_value = 1 if check.status == 'healthy' else 0
                elif alert.metric in check.details:
                    metric_value = check.details[alert.metric]
                
                if metric_value is None:
                    continue
                
                # Check threshold
                triggered = False
                if alert.comparison == 'gt' and metric_value > alert.threshold:
                    triggered = True
                elif alert.comparison == 'lt' and metric_value < alert.threshold:
                    triggered = True
                elif alert.comparison == 'eq' and metric_value == alert.threshold:
                    triggered = True
                
                if triggered:
                    triggered_alerts.append({
                        'alert': alert,
                        'check': check,
                        'metric_value': metric_value,
                        'timestamp': datetime.now()
                    })
        
        return triggered_alerts
    
    def send_notifications(self, alerts: List[Dict[str, Any]]):
        """Send notifications for triggered alerts"""
        if not alerts:
            return
        
        # Group alerts by severity
        critical_alerts = [a for a in alerts if a['alert'].severity == 'critical']
        warning_alerts = [a for a in alerts if a['alert'].severity == 'warning']
        
        # Send email notifications
        if self.notification_config.get('email', {}).get('enabled'):
            self._send_email_notification(critical_alerts + warning_alerts)
        
        # Log alerts
        for alert_info in alerts:
            alert = alert_info['alert']
            check = alert_info['check']
            logger.error(
                f"ALERT [{alert.severity.upper()}] {alert.service}.{alert.metric} "
                f"{alert.comparison} {alert.threshold}: actual={alert_info['metric_value']} "
                f"(status: {check.status})"
            )
    
    def _send_email_notification(self, alerts: List[Dict[str, Any]]):
        """Send email notification for alerts"""
        email_config = self.notification_config.get('email', {})
        
        try:
            smtp_server = email_config['smtp_server']
            smtp_port = email_config.get('smtp_port', 587)
            username = email_config['username']
            password = email_config['password']
            recipients = email_config['recipients']
            
            # Create message
            msg = MimeMultipart()
            msg['From'] = username
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"RAG Chatbot Alert - {len(alerts)} issues detected"
            
            # Create body
            body = "RAG Chatbot Monitoring Alert\n"
            body += "=" * 40 + "\n\n"
            body += f"Timestamp: {datetime.now()}\n"
            body += f"Total alerts: {len(alerts)}\n\n"
            
            for alert_info in alerts:
                alert = alert_info['alert']
                check = alert_info['check']
                body += f"Service: {alert.service}\n"
                body += f"Metric: {alert.metric}\n"
                body += f"Threshold: {alert.comparison} {alert.threshold}\n"
                body += f"Actual: {alert_info['metric_value']}\n"
                body += f"Severity: {alert.severity}\n"
                body += f"Status: {check.status}\n"
                body += "-" * 20 + "\n"
            
            msg.attach(MimeText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email notification sent to {len(recipients)} recipients")
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
    def generate_report(self, health_checks: List[HealthCheck]) -> str:
        """Generate monitoring report"""
        report = []
        report.append("RAG Chatbot System Monitoring Report")
        report.append("=" * 50)
        report.append(f"Generated: {datetime.now()}")
        report.append("")
        
        # Summary
        healthy_services = [c for c in health_checks if c.status == 'healthy']
        degraded_services = [c for c in health_checks if c.status == 'degraded']
        unhealthy_services = [c for c in health_checks if c.status == 'unhealthy']
        
        report.append(f"Summary:")
        report.append(f"  Healthy: {len(healthy_services)}")
        report.append(f"  Degraded: {len(degraded_services)}")
        report.append(f"  Unhealthy: {len(unhealthy_services)}")
        report.append("")
        
        # Detailed results
        for check in health_checks:
            status_icon = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(check.status, "❓")
            report.append(f"{status_icon} {check.service} ({check.status})")
            
            if check.response_time > 0:
                report.append(f"   Response time: {check.response_time:.2f}s")
            
            # Show key details
            for key, value in check.details.items():
                if isinstance(value, (int, float)):
                    report.append(f"   {key}: {value}")
                elif isinstance(value, str) and len(value) < 100:
                    report.append(f"   {key}: {value}")
            
            report.append("")
        
        return "\n".join(report)
    
    def run_monitoring_cycle(self):
        """Run one complete monitoring cycle"""
        logger.info("Starting monitoring cycle")
        
        health_checks = []
        
        # Check configured services
        for service_name, service_config in self.services.items():
            if service_config.get('enabled', True):
                check = self.check_service_health(service_name, service_config)
                health_checks.append(check)
                logger.info(f"{service_name}: {check.status} ({check.response_time:.2f}s)")
        
        # Check Docker containers
        docker_checks = self.check_docker_containers()
        health_checks.extend(docker_checks)
        
        # Check system resources
        system_check = self.check_system_resources()
        health_checks.append(system_check)
        logger.info(f"System resources: {system_check.status}")
        
        # Run performance test (optional)
        if self.config.get('performance_test', {}).get('enabled', False):
            perf_check = self.run_performance_test()
            health_checks.append(perf_check)
            logger.info(f"Performance test: {perf_check.status}")
        
        # Evaluate alerts
        triggered_alerts = self.evaluate_alerts(health_checks)
        
        # Send notifications if needed
        if triggered_alerts:
            self.send_notifications(triggered_alerts)
        
        # Generate and save report
        report = self.generate_report(health_checks)
        
        if self.config.get('save_reports', True):
            report_file = f"monitoring_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, 'w') as f:
                f.write(report)
            logger.info(f"Report saved to {report_file}")
        
        logger.info(f"Monitoring cycle completed - {len(triggered_alerts)} alerts triggered")
        return health_checks, triggered_alerts


def load_config(config_file: str) -> Dict[str, Any]:
    """Load monitoring configuration from file"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config file {config_file}: {e}")
        return {}


def create_default_config() -> Dict[str, Any]:
    """Create default monitoring configuration"""
    return {
        "services": {
            "fastapi": {
                "enabled": True,
                "health_url": "http://localhost:8000/health",
                "chat_url": "http://localhost:8000/chat",
                "timeout": 10
            },
            "streamlit": {
                "enabled": True,
                "health_url": "http://localhost:8501",
                "timeout": 10
            },
            "airflow": {
                "enabled": True,
                "health_url": "http://localhost:8080/health",
                "timeout": 10
            },
            "qdrant": {
                "enabled": True,
                "health_url": "http://localhost:6333/health",
                "timeout": 10
            }
        },
        "alerts": [
            {
                "service": "fastapi",
                "metric": "response_time",
                "threshold": 5.0,
                "comparison": "gt",
                "severity": "warning"
            },
            {
                "service": "system_resources",
                "metric": "cpu_percent",
                "threshold": 85.0,
                "comparison": "gt",
                "severity": "critical"
            },
            {
                "service": "system_resources",
                "metric": "memory_percent",
                "threshold": 85.0,
                "comparison": "gt",
                "severity": "critical"
            }
        ],
        "notifications": {
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "your-email@gmail.com",
                "password": "your-password",
                "recipients": ["admin@yourcompany.com"]
            }
        },
        "performance_test": {
            "enabled": True
        },
        "save_reports": True,
        "monitoring_interval": 300
    }


def main():
    parser = argparse.ArgumentParser(description="RAG Chatbot System Monitor")
    parser.add_argument('--config', '-c', default='monitoring_config.json',
                       help='Configuration file path')
    parser.add_argument('--create-config', action='store_true',
                       help='Create default configuration file')
    parser.add_argument('--daemon', '-d', action='store_true',
                       help='Run as daemon')
    parser.add_argument('--interval', '-i', type=int, default=300,
                       help='Monitoring interval in seconds (daemon mode)')
    
    args = parser.parse_args()
    
    if args.create_config:
        config = create_default_config()
        with open(args.config, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"Default configuration created: {args.config}")
        return
    
    # Load configuration
    config = load_config(args.config)
    if not config:
        print(f"Failed to load config. Create one with: {parser.prog} --create-config")
        return
    
    # Create monitor
    monitor = RAGMonitor(config)
    
    if args.daemon:
        # Daemon mode
        interval = args.interval or config.get('monitoring_interval', 300)
        logger.info(f"Starting daemon mode with {interval}s interval")
        
        try:
            while True:
                try:
                    monitor.run_monitoring_cycle()
                except Exception as e:
                    logger.error(f"Error in monitoring cycle: {e}")
                
                logger.info(f"Waiting {interval} seconds until next cycle...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring daemon stopped")
    else:
        # Single run mode
        health_checks, alerts = monitor.run_monitoring_cycle()
        
        # Print summary
        print(f"\n✅ Healthy: {len([c for c in health_checks if c.status == 'healthy'])}")
        print(f"⚠️  Degraded: {len([c for c in health_checks if c.status == 'degraded'])}")
        print(f"❌ Unhealthy: {len([c for c in health_checks if c.status == 'unhealthy'])}")
        print(f"🚨 Alerts: {len(alerts)}")


if __name__ == "__main__":
    main()