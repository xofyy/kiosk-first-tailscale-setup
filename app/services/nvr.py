"""
NVR Camera Service
ISAPI channel discovery and go2rtc stream management
"""

import logging
import requests
from requests.auth import HTTPDigestAuth
from typing import Dict, List, Any, Optional
from xml.etree import ElementTree

from app.modules.base import mongo_config as config

logger = logging.getLogger(__name__)

# Timeouts (seconds)
ISAPI_TIMEOUT = 10
GO2RTC_TIMEOUT = 5

# go2rtc API URL (host network mode, local access)
GO2RTC_API_URL = 'http://localhost:1984'

# ISAPI via nginx proxy (nginx proxies localhost:8080 -> NVR)
ISAPI_BASE_URL = 'http://localhost:8080'

# RTSP via nginx proxy (nginx proxies localhost:554 -> NVR)
RTSP_HOST = 'localhost'
RTSP_PORT = 554


class NvrService:
    """NVR camera management via ISAPI and go2rtc"""

    def __init__(self):
        self._go2rtc_url = GO2RTC_API_URL
        self._isapi_url = ISAPI_BASE_URL

    def _get_credentials(self) -> tuple:
        """Get NVR credentials from MongoDB config"""
        config.reload()
        username = config.get('nvr.username', '')
        password = config.get('nvr.password', '')
        return username, password

    def _get_digest_auth(self) -> Optional[HTTPDigestAuth]:
        """Create digest auth from stored credentials"""
        username, password = self._get_credentials()
        if not username or not password:
            return None
        return HTTPDigestAuth(username, password)

    # =========================================================================
    # ISAPI Methods
    # =========================================================================

    def test_connection(self) -> Dict[str, Any]:
        """
        Test NVR connection via ISAPI deviceInfo endpoint.
        Returns dict with success status and device info.
        """
        auth = self._get_digest_auth()
        if not auth:
            return {'success': False, 'error': 'NVR credentials not configured'}

        try:
            response = requests.get(
                f'{self._isapi_url}/ISAPI/System/deviceInfo',
                auth=auth,
                timeout=ISAPI_TIMEOUT
            )

            if response.status_code == 200:
                root = ElementTree.fromstring(response.text)
                ns = self._get_namespace(root)

                device_name = self._xml_find_text(root, f'{ns}deviceName', 'Unknown')
                model = self._xml_find_text(root, f'{ns}model', 'Unknown')
                serial = self._xml_find_text(root, f'{ns}serialNumber', '')

                return {
                    'success': True,
                    'device_name': device_name,
                    'model': model,
                    'serial_number': serial
                }
            elif response.status_code == 401:
                return {'success': False, 'error': 'Authentication failed (wrong username/password)'}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Connection timeout'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Cannot connect to NVR (check nginx proxy)'}
        except Exception as e:
            logger.error(f"NVR connection test error: {e}")
            return {'success': False, 'error': str(e)}

    def discover_channels(self) -> Dict[str, Any]:
        """
        Discover camera channels via ISAPI/Streaming/channels.
        Returns dict with success and channel list.
        """
        auth = self._get_digest_auth()
        if not auth:
            return {'success': False, 'error': 'NVR credentials not configured', 'channels': []}

        try:
            response = requests.get(
                f'{self._isapi_url}/ISAPI/Streaming/channels',
                auth=auth,
                timeout=ISAPI_TIMEOUT
            )

            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'ISAPI error: HTTP {response.status_code}',
                    'channels': []
                }

            channels = self._parse_channels_xml(response.text)
            return {'success': True, 'channels': channels}

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'ISAPI timeout', 'channels': []}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Cannot connect to NVR', 'channels': []}
        except Exception as e:
            logger.error(f"Channel discovery error: {e}")
            return {'success': False, 'error': str(e), 'channels': []}

    def _parse_channels_xml(self, xml_text: str) -> List[Dict[str, Any]]:
        """Parse ISAPI Streaming/channels XML response.

        Raises exceptions on parse errors - caller should handle.
        """
        channels = []
        root = ElementTree.fromstring(xml_text)

        # Find StreamingChannel elements (may have different namespace than root)
        channel_elements = root.findall(f'{self._get_namespace(root)}StreamingChannel')
        if not channel_elements:
            # Hikvision NVRs use different namespaces for root vs children
            channel_elements = root.findall('.//{http://www.isapi.org/ver20/XMLSchema}StreamingChannel')

        for ch in channel_elements:
            ns = self._get_namespace(ch)
            ch_id_text = self._xml_find_text(ch, f'{ns}id', '0')
            ch_id = int(ch_id_text)
            channel_no = ch_id // 100
            stream_type = ch_id % 100

            # Parse Video element
            video_info = {}
            video_el = ch.find(f'{ns}Video')
            if video_el is not None:
                video_info = {
                    'codec': self._xml_find_text(video_el, f'{ns}videoCodecType', ''),
                    'width': self._xml_find_int(video_el, f'{ns}videoResolutionWidth', 0),
                    'height': self._xml_find_int(video_el, f'{ns}videoResolutionHeight', 0),
                    'fps': self._xml_find_int(video_el, f'{ns}maxFrameRate', 0),
                    'bitrate': self._xml_find_int(video_el, f'{ns}vbrUpperCap', 0),
                }

            enabled = self._xml_find_text(ch, f'{ns}enabled', 'false')
            channel_name = self._xml_find_text(ch, f'{ns}channelName', f'Channel {channel_no}')

            channels.append({
                'id': ch_id,
                'channel_no': channel_no,
                'stream_type': stream_type,
                'name': channel_name,
                'enabled': enabled.lower() == 'true',
                'video': video_info
            })

        return channels

    # =========================================================================
    # go2rtc Stream Management
    # =========================================================================

    def start_stream(self, channel_id: int) -> Dict[str, Any]:
        """
        Create a stream in go2rtc for the given channel.
        RTSP URL goes through nginx proxy (localhost:554).
        Returns stream name and go2rtc URL on success.
        """
        username, password = self._get_credentials()
        if not username or not password:
            return {'success': False, 'error': 'NVR credentials not configured'}

        stream_name = f'camera_{channel_id}'
        rtsp_url = (
            f'ffmpeg:rtsp://{username}:{password}@{RTSP_HOST}:{RTSP_PORT}'
            f'/ISAPI/Streaming/channels/{channel_id}#video=h264'
        )

        try:
            response = requests.put(
                f'{self._go2rtc_url}/api/streams',
                params={'src': rtsp_url, 'name': stream_name},
                timeout=GO2RTC_TIMEOUT
            )

            if response.status_code in (200, 201):
                logger.info(f"Stream started: {stream_name} (channel {channel_id})")
                return {
                    'success': True,
                    'stream_name': stream_name,
                    'channel_id': channel_id,
                    'go2rtc_url': self._go2rtc_url
                }
            else:
                return {
                    'success': False,
                    'error': f'go2rtc error: HTTP {response.status_code}'
                }

        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'go2rtc is not running'}
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'go2rtc timeout'}
        except Exception as e:
            logger.error(f"Stream start error: {e}")
            return {'success': False, 'error': str(e)}

    def stop_stream(self, stream_name: str) -> Dict[str, Any]:
        """Remove a stream from go2rtc"""
        try:
            requests.delete(
                f'{self._go2rtc_url}/api/streams',
                params={'src': stream_name},
                timeout=GO2RTC_TIMEOUT
            )

            logger.info(f"Stream stopped: {stream_name}")
            return {'success': True}

        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'go2rtc is not running'}
        except Exception as e:
            logger.error(f"Stream stop error: {e}")
            return {'success': False, 'error': str(e)}

    def get_active_streams(self) -> Dict[str, Any]:
        """Get all active streams from go2rtc"""
        try:
            response = requests.get(
                f'{self._go2rtc_url}/api/streams',
                timeout=GO2RTC_TIMEOUT
            )

            if response.status_code == 200:
                return {'success': True, 'streams': response.json()}
            return {'success': False, 'streams': {}}

        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'go2rtc is not running', 'streams': {}}
        except Exception as e:
            logger.error(f"Get streams error: {e}")
            return {'success': False, 'error': str(e), 'streams': {}}

    def stop_all_streams(self) -> Dict[str, Any]:
        """Stop all camera_ prefixed streams"""
        result = self.get_active_streams()
        if not result.get('success'):
            return result

        stopped = []
        for name in result.get('streams', {}).keys():
            if name.startswith('camera_'):
                self.stop_stream(name)
                stopped.append(name)

        return {'success': True, 'stopped': stopped}

    # =========================================================================
    # XML Helper Methods
    # =========================================================================

    @staticmethod
    def _get_namespace(element) -> str:
        """Extract XML namespace from root element"""
        tag = element.tag
        if tag.startswith('{'):
            return tag.split('}')[0] + '}'
        return ''

    @staticmethod
    def _xml_find_text(element, tag: str, default: str = '') -> str:
        """Safely find text in XML element"""
        el = element.find(tag)
        return el.text if el is not None and el.text else default

    @staticmethod
    def _xml_find_int(element, tag: str, default: int = 0) -> int:
        """Safely find integer in XML element"""
        el = element.find(tag)
        if el is not None and el.text:
            try:
                return int(el.text)
            except ValueError:
                pass
        return default
