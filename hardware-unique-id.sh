#!/bin/bash

# ============================================================================
# Hardware-Based Unique ID Generator for Ubuntu Servers
# ID için kullanılan: Anakart Seri No, RAM Seri No, Disk Seri No
# Diğer bilgiler sadece gösterim amaçlı
# ============================================================================

# Renk kodları
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ID için kullanılan bilgi etiketi
ID_TAG="${GREEN}[ID]${NC}"

# ============================================================================
# ANAKART BİLGİLERİ
# ============================================================================

get_motherboard_serial() {
    dmidecode -s baseboard-serial-number 2>/dev/null || echo ""
}

show_motherboard_info() {
    echo -e "${CYAN}[ANAKART]${NC}"
    echo "  System UUID:      $(dmidecode -s system-uuid 2>/dev/null || echo 'N/A')"
    echo "  Üretici:          $(dmidecode -s baseboard-manufacturer 2>/dev/null || echo 'N/A')"
    echo "  Model:            $(dmidecode -s baseboard-product-name 2>/dev/null || echo 'N/A')"
    echo -e "  Seri No:          $(dmidecode -s baseboard-serial-number 2>/dev/null || echo 'N/A') $ID_TAG"
    echo "  Versiyon:         $(dmidecode -s baseboard-version 2>/dev/null || echo 'N/A')"
    echo ""
}

# ============================================================================
# CPU BİLGİLERİ
# ============================================================================

show_cpu_info() {
    echo -e "${CYAN}[CPU]${NC} ${YELLOW}(ID'ye dahil değil)${NC}"
    echo "  Model:            $(grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo 'N/A')"
    echo "  Microcode:        $(grep -m1 "microcode" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo 'N/A')"
    echo "  Fiziksel CPU:     $(grep "physical id" /proc/cpuinfo 2>/dev/null | sort -u | wc -l || echo 'N/A')"
    echo "  Toplam Core:      $(grep -c "^processor" /proc/cpuinfo 2>/dev/null || echo 'N/A')"
    echo ""
}

# ============================================================================
# RAM BİLGİLERİ
# ============================================================================

get_ram_serials() {
    dmidecode -t memory 2>/dev/null | grep "Serial Number" | grep -v "Not Specified" | awk '{print $3}' | sort | tr '\n' ',' | sed 's/,$//'
}

show_ram_info() {
    echo -e "${CYAN}[RAM]${NC}"
    
    # Toplam RAM
    echo "  Toplam:           $(free -h 2>/dev/null | grep Mem | awk '{print $2}' || echo 'N/A')"
    
    # dmidecode çıktısını dosyaya yaz
    local tmpfile="/tmp/meminfo_$$"
    dmidecode -t memory > "$tmpfile" 2>/dev/null
    
    # Memory Device bloklarının başlangıç satır numaralarını bul
    local line_numbers=$(grep -n "^Memory Device" "$tmpfile" | cut -d: -f1)
    local module_num=0
    
    for start in $line_numbers; do
        local block=$(sed -n "${start},$((start + 50))p" "$tmpfile")
        local size=$(echo "$block" | grep "Size:" | head -1 | sed 's/.*Size: //')
        
        # Boş slotları atla
        if [[ "$size" == *"No Module"* ]] || [[ "$size" == "None" ]] || [[ -z "$size" ]]; then
            continue
        fi
        
        module_num=$((module_num + 1))
        
        local locator=$(echo "$block" | grep "Locator:" | grep -v "Bank" | head -1 | sed 's/.*Locator: //')
        local mtype=$(echo "$block" | grep "Type:" | grep -v "Error\|Detail" | head -1 | sed 's/.*Type: //')
        local speed=$(echo "$block" | grep "Speed:" | grep -v "Configured" | head -1 | sed 's/.*Speed: //')
        local manufacturer=$(echo "$block" | grep "Manufacturer:" | head -1 | sed 's/.*Manufacturer: //')
        local serial=$(echo "$block" | grep "Serial Number:" | head -1 | sed 's/.*Serial Number: //')
        
        if [[ -n "$locator" && "$locator" != "Not Specified" ]]; then
            echo "  Modül $module_num ($locator):"
        else
            echo "  Modül $module_num:"
        fi
        echo "    Boyut:          $size"
        [[ -n "$mtype" && "$mtype" != "Unknown" ]] && echo "    Tip:            $mtype"
        [[ -n "$speed" && "$speed" != "Unknown" ]] && echo "    Hız:            $speed"
        [[ -n "$manufacturer" && "$manufacturer" != "Not Specified" ]] && echo "    Üretici:        $manufacturer"
        if [[ -n "$serial" && "$serial" != "Not Specified" ]]; then
            echo -e "    Seri No:        $serial $ID_TAG"
        fi
    done
    
    rm -f "$tmpfile"
    echo ""
}

# ============================================================================
# DİSK BİLGİLERİ
# ============================================================================

get_disk_serials() {
    lsblk -d -o SERIAL -n 2>/dev/null | grep -v "^$" | sort | tr '\n' ',' | sed 's/,$//'
}

show_disk_info() {
    echo -e "${CYAN}[DİSK]${NC}"
    
    lsblk -d -o NAME,SERIAL,MODEL,SIZE -n 2>/dev/null | grep -vE "^loop|^ram" | while read -r name serial model size; do
        echo "  /dev/$name:"
        echo "    Model:          $model"
        if [[ -n "$serial" ]]; then
            echo -e "    Seri No:        $serial $ID_TAG"
        else
            echo "    Seri No:        N/A"
        fi
        echo "    Boyut:          $size"
    done
    echo ""
}

# ============================================================================
# ETHERNET KARTI BİLGİLERİ
# ============================================================================

show_ethernet_info() {
    echo -e "${CYAN}[ETHERNET KARTLARI]${NC} ${YELLOW}(ID'ye dahil değil)${NC}"
    
    local count=0
    for iface in $(ls /sys/class/net/ 2>/dev/null | grep -vE "^(lo|docker|br-|veth|virbr)" | sort); do
        if [[ -d "/sys/class/net/$iface/device" ]]; then
            count=$((count + 1))
            local mac=$(cat /sys/class/net/$iface/address 2>/dev/null || echo "N/A")
            local driver=$(basename $(readlink /sys/class/net/$iface/device/driver 2>/dev/null) 2>/dev/null || echo "N/A")
            local state=$(cat /sys/class/net/$iface/operstate 2>/dev/null || echo "N/A")
            
            echo "  Kart $count ($iface):"
            echo "    MAC Adresi:     $mac"
            echo "    Sürücü:         $driver"
            echo "    Durum:          $state"
        fi
    done
    
    [[ $count -eq 0 ]] && echo "  Fiziksel ethernet kartı bulunamadı"
    echo ""
}

# ============================================================================
# GPU BİLGİLERİ
# ============================================================================

show_gpu_info() {
    echo -e "${CYAN}[GPU]${NC} ${YELLOW}(ID'ye dahil değil)${NC}"
    
    local count=0
    lspci 2>/dev/null | grep -iE "(vga|3d|display)" | while read -r line; do
        count=$((count + 1))
        echo "  GPU $count:           $line"
    done
    
    if command -v nvidia-smi &>/dev/null; then
        echo ""
        echo "  NVIDIA Detay:"
        nvidia-smi --query-gpu=name,gpu_uuid,memory.total --format=csv,noheader 2>/dev/null | while IFS=, read -r name uuid memory; do
            echo "    Model:          $name"
            echo "    UUID:           $uuid"
            echo "    Bellek:         $memory"
        done
    fi
    
    echo ""
}

# ============================================================================
# ID ÜRETME (Sadece Seri Numaraları)
# ============================================================================

generate_full_hardware_id() {
    local all=""
    all+="MOBO_SERIAL:$(get_motherboard_serial)|"
    all+="RAM_SERIALS:$(get_ram_serials)|"
    all+="DISK_SERIALS:$(get_disk_serials)"
    
    echo -n "$all" | sha256sum | cut -d' ' -f1
}

generate_short_id() {
    generate_full_hardware_id | cut -c1-16
}

generate_md5_id() {
    local all=""
    all+="$(get_motherboard_serial)"
    all+="$(get_ram_serials)"
    all+="$(get_disk_serials)"
    
    echo -n "$all" | md5sum | cut -d' ' -f1
}

# ============================================================================
# JSON ÇIKTI
# ============================================================================

output_json() {
    local mobo_uuid=$(dmidecode -s system-uuid 2>/dev/null || echo "N/A")
    local mobo_serial=$(dmidecode -s baseboard-serial-number 2>/dev/null || echo "N/A")
    local mobo_vendor=$(dmidecode -s baseboard-manufacturer 2>/dev/null || echo "N/A")
    local mobo_model=$(dmidecode -s baseboard-product-name 2>/dev/null || echo "N/A")
    
    local cpu_model=$(grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "N/A")
    local cpu_cores=$(grep -c "^processor" /proc/cpuinfo 2>/dev/null || echo "0")
    
    local total_ram=$(free -h 2>/dev/null | grep Mem | awk '{print $2}' || echo "N/A")
    local ram_serials=$(get_ram_serials)
    
    # Ethernet JSON
    local eth_json="["
    local first=true
    for iface in $(ls /sys/class/net/ 2>/dev/null | grep -vE "^(lo|docker|br-|veth|virbr)" | sort); do
        if [[ -d "/sys/class/net/$iface/device" ]]; then
            local mac=$(cat /sys/class/net/$iface/address 2>/dev/null || echo "")
            local driver=$(basename $(readlink /sys/class/net/$iface/device/driver 2>/dev/null) 2>/dev/null || echo "")
            [[ "$first" == "true" ]] && first=false || eth_json+=","
            eth_json+="{\"interface\":\"$iface\",\"mac\":\"$mac\",\"driver\":\"$driver\"}"
        fi
    done
    eth_json+="]"
    
    # Disk JSON
    local disk_json=$(lsblk -d -o NAME,SERIAL,MODEL,SIZE -n 2>/dev/null | grep -vE "^loop|^ram" | awk 'BEGIN{printf "["} NR>1{printf ","} {printf "{\"device\":\"/dev/%s\",\"serial\":\"%s\",\"model\":\"%s\",\"size\":\"%s\"}",$1,$2,$3,$4} END{printf "]"}')
    
    local gpu_info=$(lspci 2>/dev/null | grep -iE "(vga|3d|display)" | head -1 | sed 's/"/\\"/g' || echo "N/A")
    
    cat << EOF
{
    "unique_ids": {
        "full_sha256": "$(generate_full_hardware_id)",
        "short_id": "$(generate_short_id)",
        "md5_id": "$(generate_md5_id)"
    },
    "id_components": {
        "motherboard_serial": "$mobo_serial",
        "ram_serials": "$ram_serials",
        "disk_serials": "$(get_disk_serials)"
    },
    "all_components": {
        "motherboard": {
            "uuid": "$mobo_uuid",
            "serial": "$mobo_serial",
            "vendor": "$mobo_vendor",
            "model": "$mobo_model"
        },
        "cpu": {
            "model": "$cpu_model",
            "cores": $cpu_cores
        },
        "ram": {
            "total": "$total_ram",
            "serials": "$ram_serials"
        },
        "disks": $disk_json,
        "ethernet": $eth_json,
        "gpu": "$gpu_info"
    },
    "generated_at": "$(date -Iseconds)",
    "hostname": "$(hostname)"
}
EOF
}

# ============================================================================
# RAW DATA GÖSTER (Debug için)
# ============================================================================

show_raw_data() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║           ID İÇİN KULLANILAN RAW DATA                         ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "MOBO_SERIAL:  $(get_motherboard_serial)"
    echo "RAM_SERIALS:  $(get_ram_serials)"
    echo "DISK_SERIALS: $(get_disk_serials)"
    echo ""
}

# ============================================================================
# GÖSTER
# ============================================================================

show_all() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║           DONANIM BİLEŞENLERİ DETAYI                          ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Not: ${ID_TAG} işaretli değerler ID üretiminde kullanılır${NC}"
    echo ""
    
    show_motherboard_info
    show_cpu_info
    show_ram_info
    show_disk_info
    show_ethernet_info
    show_gpu_info
}

show_ids() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║           ÜRETİLEN UNIQUE ID'LER                              ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    echo -e "${GREEN}Full Hardware ID (SHA256):${NC}"
    echo "  $(generate_full_hardware_id)"
    echo ""
    
    echo -e "${GREEN}Short ID (16 karakter):${NC}"
    echo "  $(generate_short_id)"
    echo ""
    
    echo -e "${GREEN}MD5 ID (32 karakter):${NC}"
    echo "  $(generate_md5_id)"
    echo ""
}

print_usage() {
    echo "Kullanım: sudo $0 [SEÇENEK]"
    echo ""
    echo "  (yok)       Tüm bileşenler + ID'ler"
    echo "  --show      Sadece bileşen bilgileri"
    echo "  --id        Sadece SHA256 ID"
    echo "  --short     Kısa ID (16 kar)"
    echo "  --md5       MD5 ID (32 kar)"
    echo "  --json      JSON formatı"
    echo "  --raw       ID için kullanılan raw data"
    echo "  --help      Yardım"
}

# ============================================================================
# MAIN
# ============================================================================

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Hata: Root yetkisi gerekli. sudo ile çalıştırın.${NC}"
    exit 1
fi

case "${1:-}" in
    --show|-s)   show_all ;;
    --id)        generate_full_hardware_id ;;
    --short)     generate_short_id ;;
    --md5)       generate_md5_id ;;
    --json|-j)   output_json ;;
    --raw|-r)    show_raw_data ;;
    --help|-h)   print_usage ;;
    "")          show_all; show_ids ;;
    *)           echo "Bilinmeyen: $1"; print_usage; exit 1 ;;
esac