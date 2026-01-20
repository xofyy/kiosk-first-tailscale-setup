"""
ACO Maintenance Panel - Enrollment Service
Enrollment API client
"""

import time
import logging
import warnings
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

ENROLLMENT_API_URL = "https://enrollment.xofyy.com"
ENROLLMENT_TIMEOUT = 30


class EnrollmentService:
    """Enrollment API client"""
    
    def __init__(self, api_url: str = ENROLLMENT_API_URL):
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def close(self) -> None:
        """Close session"""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def enroll(self, rvm_id: str, hardware_id: str, motherboard_uuid: str = '', mac_addresses: str = '') -> Dict[str, Any]:
        """
        Send enrollment request to API.

        Args:
            rvm_id: RVM ID (sent as hostname)
            hardware_id: Hardware ID
            motherboard_uuid: Motherboard UUID
            mac_addresses: MAC addresses (comma-separated)

        Returns:
            API response (success, status, auth_key, data)
        """
        try:
            logger.info(f"Sending enrollment request: hardware_id={hardware_id}, hostname={rvm_id}")

            response = self.session.post(
                f"{self.api_url}/api/enroll",
                json={
                    'hardware_id': hardware_id,
                    'hostname': rvm_id,
                    'motherboard_uuid': motherboard_uuid,
                    'mac_addresses': mac_addresses
                },
                timeout=ENROLLMENT_TIMEOUT
            )
            
            logger.info(f"Enrollment response: status_code={response.status_code}")

            if response.status_code in (200, 201):
                resp_data = response.json()
                # Parse nested data structure (API: { data: { status, auth_key } })
                inner_data = resp_data.get('data', resp_data)
                status = inner_data.get('status')
                auth_key = inner_data.get('auth_key')
                
                logger.info(f"Enrollment status: status={status}, auth_key={'present' if auth_key else 'none'}")

                return {
                    'success': True,
                    'status': status,
                    'auth_key': auth_key,  # Key is here if already approved
                    'data': inner_data
                }
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', 'Validation error')
                except (ValueError, KeyError):
                    error_msg = 'Validation error'
                logger.error(f"Validation error: {error_msg}")
                return {
                    'success': False,
                    'error': f"Validation error: {error_msg}",
                    'details': response.text
                }
            elif response.status_code == 429:
                logger.warning("Rate limit exceeded")
                return {
                    'success': False,
                    'error': 'Too many requests, please wait'
                }
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"API error: {response.status_code}",
                    'details': response.text
                }

        except requests.exceptions.Timeout:
            logger.error("Connection timeout")
            return {
                'success': False,
                'error': 'Connection timeout'
            }
        except requests.exceptions.ConnectionError:
            logger.error("Connection failed")
            return {
                'success': False,
                'error': 'Connection failed'
            }
        except Exception as e:
            logger.error(f"Enrollment error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_status(self, hardware_id: str) -> Dict[str, Any]:
        """
        Check enrollment status.

        Args:
            hardware_id: Hardware ID (query with HARDWARE_ID!)

        Returns:
            Status info (pending, approved, rejected, expired)
        """
        try:
            # CORRECT ENDPOINT: /api/enroll/{hardware_id}/status
            response = self.session.get(
                f"{self.api_url}/api/enroll/{hardware_id}/status",
                timeout=ENROLLMENT_TIMEOUT
            )
            
            if response.status_code == 200:
                resp_data = response.json()
                # Parse nested data structure (API: { data: { status, auth_key } })
                inner_data = resp_data.get('data', resp_data)

                return {
                    'success': True,
                    'status': inner_data.get('status'),
                    'auth_key': inner_data.get('auth_key'),
                    'reason': inner_data.get('reason'),  # For rejected status
                    'data': inner_data
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': 'Registration not found'
                }
            else:
                return {
                    'success': False,
                    'error': f"API error: {response.status_code}"
                }

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Connection timeout'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Connection failed'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def wait_for_approval(
        self,
        hardware_id: str,
        timeout: int = 300,
        poll_interval: int = 30
    ) -> Optional[str]:
        """
        Wait for admin approval and get auth key.

        Args:
            hardware_id: Hardware ID (query with HARDWARE_ID!)
            timeout: Maximum wait time (seconds)
            poll_interval: Check interval (seconds) - default 30s

        Returns:
            Tailscale auth key or None (timeout/rejected)
        """
        start_time = time.time()

        logger.info(f"Waiting for admin approval... (max {timeout}s, checking every {poll_interval}s)")

        while time.time() - start_time < timeout:
            # Status check with HARDWARE_ID
            status_result = self.check_status(hardware_id)

            if not status_result.get('success'):
                logger.warning(f"Status check failed: {status_result.get('error')}")
                time.sleep(poll_interval)
                continue

            enrollment_status = status_result.get('status')

            if enrollment_status == 'approved':
                logger.info("Approval received!")
                # Auth key is in STATUS response (not separate endpoint!)
                auth_key = status_result.get('auth_key')
                if auth_key:
                    return auth_key
                logger.error("Approval received but auth_key not found!")
                return None

            elif enrollment_status == 'rejected':
                reason = status_result.get('reason', 'Unknown')
                logger.error(f"Registration rejected: {reason}")
                return None

            elif enrollment_status == 'expired':
                logger.warning("Auth key expired, waiting for new approval...")

            # pending - continue waiting
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            logger.info(f"Waiting... ({remaining}s remaining)")

            time.sleep(poll_interval)

        logger.error("Timeout - approval not received")
        return None
    
    def cancel_enrollment(self, rvm_id: str) -> bool:
        """
        Cancel enrollment request.

        Args:
            rvm_id: RVM ID

        Returns:
            Success status
        """
        try:
            response = self.session.delete(
                f"{self.api_url}/api/enroll/{rvm_id}",
                timeout=ENROLLMENT_TIMEOUT
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False
