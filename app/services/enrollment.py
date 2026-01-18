"""
Kiosk Setup Panel - Enrollment Service
Enrollment API istemcisi
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
    """Enrollment API istemcisi"""
    
    def __init__(self, api_url: str = ENROLLMENT_API_URL):
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def close(self) -> None:
        """Session'ı kapat"""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def enroll(self, kiosk_id: str, hardware_id: str, motherboard_uuid: str = '', mac_addresses: str = '') -> Dict[str, Any]:
        """
        Enrollment API'ye kayıt isteği gönder.
        
        Args:
            kiosk_id: Kiosk kimliği (hostname olarak gönderilir)
            hardware_id: Donanım kimliği
            motherboard_uuid: Anakart UUID'si
            mac_addresses: MAC adresleri (virgülle ayrılmış)
            
        Returns:
            API yanıtı (success, status, auth_key, data)
        """
        try:
            logger.info(f"Enrollment isteği gönderiliyor: hardware_id={hardware_id}, hostname={kiosk_id}")
            
            response = self.session.post(
                f"{self.api_url}/api/enroll",
                json={
                    'hardware_id': hardware_id,
                    'hostname': kiosk_id,
                    'motherboard_uuid': motherboard_uuid,
                    'mac_addresses': mac_addresses
                },
                timeout=ENROLLMENT_TIMEOUT
            )
            
            logger.info(f"Enrollment yanıtı: status_code={response.status_code}")
            
            if response.status_code in (200, 201):
                resp_data = response.json()
                # Nested data yapısını parse et (API: { data: { status, auth_key } })
                inner_data = resp_data.get('data', resp_data)
                status = inner_data.get('status')
                auth_key = inner_data.get('auth_key')
                
                logger.info(f"Enrollment durumu: status={status}, auth_key={'var' if auth_key else 'yok'}")
                
                return {
                    'success': True,
                    'status': status,
                    'auth_key': auth_key,  # Zaten approved ise key burada
                    'data': inner_data
                }
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', 'Doğrulama hatası')
                except (ValueError, KeyError):
                    error_msg = 'Doğrulama hatası'
                logger.error(f"Validation hatası: {error_msg}")
                return {
                    'success': False,
                    'error': f"Validation hatası: {error_msg}",
                    'details': response.text
                }
            elif response.status_code == 429:
                logger.warning("Rate limit aşıldı")
                return {
                    'success': False,
                    'error': 'Çok fazla istek gönderildi, lütfen bekleyin'
                }
            else:
                logger.error(f"API hatası: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"API hatası: {response.status_code}",
                    'details': response.text
                }
                
        except requests.exceptions.Timeout:
            logger.error("Bağlantı zaman aşımı")
            return {
                'success': False,
                'error': 'Bağlantı zaman aşımı'
            }
        except requests.exceptions.ConnectionError:
            logger.error("Bağlantı kurulamadı")
            return {
                'success': False,
                'error': 'Bağlantı kurulamadı'
            }
        except Exception as e:
            logger.error(f"Enrollment hatası: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_status(self, hardware_id: str) -> Dict[str, Any]:
        """
        Enrollment durumunu kontrol et.
        
        Args:
            hardware_id: Donanım kimliği (HARDWARE_ID ile sorgulama!)
            
        Returns:
            Durum bilgisi (pending, approved, rejected, expired)
        """
        try:
            # DOĞRU ENDPOINT: /api/enroll/{hardware_id}/status
            response = self.session.get(
                f"{self.api_url}/api/enroll/{hardware_id}/status",
                timeout=ENROLLMENT_TIMEOUT
            )
            
            if response.status_code == 200:
                resp_data = response.json()
                # Nested data yapısını parse et (API: { data: { status, auth_key } })
                inner_data = resp_data.get('data', resp_data)
                
                return {
                    'success': True,
                    'status': inner_data.get('status'),
                    'auth_key': inner_data.get('auth_key'),
                    'reason': inner_data.get('reason'),  # rejected durumunda
                    'data': inner_data
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
    
    def wait_for_approval(
        self,
        hardware_id: str,
        timeout: int = 300,
        poll_interval: int = 30
    ) -> Optional[str]:
        """
        Yönetici onayını bekle ve auth key al.
        
        Args:
            hardware_id: Donanım kimliği (HARDWARE_ID ile sorgulama!)
            timeout: Maksimum bekleme süresi (saniye)
            poll_interval: Kontrol aralığı (saniye) - varsayılan 30s
            
        Returns:
            Tailscale auth key veya None (zaman aşımı/red)
        """
        start_time = time.time()
        
        logger.info(f"Yönetici onayı bekleniyor... (max {timeout}s, her {poll_interval}s kontrol)")
        
        while time.time() - start_time < timeout:
            # HARDWARE_ID ile status kontrolü
            status_result = self.check_status(hardware_id)
            
            if not status_result.get('success'):
                logger.warning(f"Durum kontrolü başarısız: {status_result.get('error')}")
                time.sleep(poll_interval)
                continue
            
            enrollment_status = status_result.get('status')
            
            if enrollment_status == 'approved':
                logger.info("Onay alındı!")
                # Auth key STATUS response'unda (ayrı endpoint değil!)
                auth_key = status_result.get('auth_key')
                if auth_key:
                    return auth_key
                logger.error("Onay alındı ama auth_key bulunamadı!")
                return None
            
            elif enrollment_status == 'rejected':
                reason = status_result.get('reason', 'Bilinmiyor')
                logger.error(f"Kayıt reddedildi: {reason}")
                return None
            
            elif enrollment_status == 'expired':
                logger.warning("Auth key süresi dolmuş, yeni onay bekleniyor...")
            
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
