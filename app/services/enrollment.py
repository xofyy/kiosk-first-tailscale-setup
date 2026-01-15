"""
Kiosk Setup Panel - Enrollment Service
Enrollment API istemcisi
"""

import time
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

ENROLLMENT_API_URL = "https://enrollment.xofyy.com"
ENROLLMENT_TIMEOUT = 30


class EnrollmentService:
    """Enrollment API istemcisi"""
    
    def __init__(self, api_url: str = ENROLLMENT_API_URL):
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def enroll(self, kiosk_id: str, hardware_id: str) -> Dict[str, Any]:
        """
        Enrollment API'ye kayıt isteği gönder.
        
        Args:
            kiosk_id: Kiosk kimliği
            hardware_id: Donanım kimliği
            
        Returns:
            API yanıtı
        """
        try:
            response = self.session.post(
                f"{self.api_url}/api/enroll",
                json={
                    'kiosk_id': kiosk_id,
                    'hardware_id': hardware_id
                },
                timeout=ENROLLMENT_TIMEOUT
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            elif response.status_code == 409:
                # Zaten kayıtlı
                return {
                    'success': True,
                    'already_enrolled': True,
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f"API hatası: {response.status_code}",
                    'details': response.text
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Bağlantı zaman aşımı'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Bağlantı kurulamadı'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_status(self, kiosk_id: str) -> Dict[str, Any]:
        """
        Enrollment durumunu kontrol et.
        
        Args:
            kiosk_id: Kiosk kimliği
            
        Returns:
            Durum bilgisi (pending, approved, rejected)
        """
        try:
            response = self.session.get(
                f"{self.api_url}/api/status/{kiosk_id}",
                timeout=ENROLLMENT_TIMEOUT
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': 'Kayıt bulunamadı'
                }
            else:
                return {
                    'success': False,
                    'error': f"API hatası: {response.status_code}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_auth_key(self, kiosk_id: str) -> Optional[str]:
        """
        Onaylanmış kayıt için auth key al.
        
        Args:
            kiosk_id: Kiosk kimliği
            
        Returns:
            Tailscale auth key veya None
        """
        try:
            response = self.session.get(
                f"{self.api_url}/api/auth-key/{kiosk_id}",
                timeout=ENROLLMENT_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('auth_key')
                
        except Exception as e:
            logger.error(f"Auth key alma hatası: {e}")
        
        return None
    
    def wait_for_approval(
        self,
        kiosk_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> Optional[str]:
        """
        Yönetici onayını bekle ve auth key al.
        
        Args:
            kiosk_id: Kiosk kimliği
            timeout: Maksimum bekleme süresi (saniye)
            poll_interval: Kontrol aralığı (saniye)
            
        Returns:
            Tailscale auth key veya None (zaman aşımı/red)
        """
        start_time = time.time()
        
        logger.info(f"Yönetici onayı bekleniyor... (max {timeout}s)")
        
        while time.time() - start_time < timeout:
            status = self.check_status(kiosk_id)
            
            if not status.get('success'):
                logger.warning(f"Durum kontrolü başarısız: {status.get('error')}")
                time.sleep(poll_interval)
                continue
            
            data = status.get('data', {})
            enrollment_status = data.get('status')
            
            if enrollment_status == 'approved':
                logger.info("Onay alındı!")
                return self.get_auth_key(kiosk_id)
            
            elif enrollment_status == 'rejected':
                logger.error("Kayıt reddedildi")
                return None
            
            # pending - beklemeye devam
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            logger.info(f"Bekleniyor... ({remaining}s kaldı)")
            
            time.sleep(poll_interval)
        
        logger.error("Zaman aşımı - onay alınamadı")
        return None
    
    def cancel_enrollment(self, kiosk_id: str) -> bool:
        """
        Enrollment isteğini iptal et.
        
        Args:
            kiosk_id: Kiosk kimliği
            
        Returns:
            Başarılı mı
        """
        try:
            response = self.session.delete(
                f"{self.api_url}/api/enroll/{kiosk_id}",
                timeout=ENROLLMENT_TIMEOUT
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"İptal hatası: {e}")
            return False
