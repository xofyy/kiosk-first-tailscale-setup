"""
Kiosk Setup Panel - Cockpit Module
Web tabanlı sunucu yönetim paneli
"""

from typing import Tuple

from app.modules import register_module
from app.modules.base import BaseModule


@register_module
class CockpitModule(BaseModule):
    name = "cockpit"
    display_name = "Cockpit"
    description = "Web tabanlı sunucu yönetim paneli"
    order = 4
    dependencies = ["network"]
    
    def install(self) -> Tuple[bool, str]:
        """Cockpit kurulumu"""
        try:
            cockpit_port = self.get_config('cockpit.port', 9090)
            
            # 1. Cockpit paketlerini kur
            self.logger.info("Cockpit kuruluyor...")
            
            packages = [
                'cockpit',
                'cockpit-system',
                'cockpit-networkmanager',
                'cockpit-storaged',
                'cockpit-packagekit'
            ]
            
            if not self.apt_install(packages):
                return False, "Cockpit paketleri kurulamadı"
            
            # 2. Cockpit socket'i etkinleştir
            self.systemctl('enable', 'cockpit.socket')
            self.systemctl('start', 'cockpit.socket')
            
            # 3. Polkit kuralı - kiosk kullanıcısına network yönetimi izni
            polkit_content = """// NetworkManager izinleri
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager") == 0 &&
        subject.user == "kiosk") {
        return polkit.Result.YES;
    }
});

// PackageKit izinleri (sınırlı)
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.packagekit") == 0 &&
        subject.user == "kiosk") {
        // Sadece görüntüleme, kurulum değil
        if (action.id == "org.freedesktop.packagekit.system-sources-refresh" ||
            action.id == "org.freedesktop.packagekit.package-info") {
            return polkit.Result.YES;
        }
    }
});
"""
            self.write_file('/etc/polkit-1/rules.d/50-kiosk-network.rules', polkit_content)
            
            # 4. Switch scriptleri
            switch_to_cockpit = f"""#!/bin/bash
# Switch to Cockpit

# Mevcut Chromium'u kapat
pkill -f chromium-browser

# Cockpit aç
exec chromium-browser \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --no-first-run \\
    "http://localhost:{cockpit_port}"
"""
            self.write_file('/usr/local/bin/switch-to-cockpit.sh', switch_to_cockpit, mode=0o755)
            
            switch_to_kiosk = """#!/bin/bash
# Switch to Kiosk

# Mevcut Chromium'u kapat
pkill -f chromium-browser

# Kiosk aç
exec /usr/local/bin/chromium-kiosk.sh
"""
            self.write_file('/usr/local/bin/switch-to-kiosk.sh', switch_to_kiosk, mode=0o755)
            
            # 5. Openbox keybinding güncelle (rc.xml zaten install.sh'de oluşturuldu)
            # Burada ek keybinding eklenebilir
            
            self.logger.info("Cockpit kurulumu tamamlandı")
            return True, f"Cockpit kuruldu. Erişim: http://localhost:{cockpit_port}"
            
        except Exception as e:
            self.logger.error(f"Cockpit kurulum hatası: {e}")
            return False, str(e)
