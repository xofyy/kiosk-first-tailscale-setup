#!/bin/bash
set -e

LV="data"
MOUNTPOINT="/data"

echo "[*] Root LVM doğrulanıyor..."
ROOT_SRC=$(findmnt -n -o SOURCE /)

# VG'yi dinamik bul (root'tan)
VG=$(lvs --noheadings -o vg_name "$ROOT_SRC" 2>/dev/null | tr -d ' ')
if [[ -z "$VG" ]]; then
  echo "[!] Root LVM değil veya VG bulunamadı: $ROOT_SRC"
  exit 1
fi
echo "[*] Volume Group: $VG"

# Disk'i PV'den bul
PV=$(pvs --noheadings -o pv_name -S vg_name="$VG" | head -1 | tr -d ' ')
if [[ -z "$PV" ]]; then
  echo "[!] PV bulunamadı: VG=$VG"
  exit 1
fi

DISK_NAME=$(lsblk -no PKNAME "$PV" | head -1)
DISK="/dev/$DISK_NAME"
echo "[*] Physical Volume: $PV (Disk: $DISK)"

echo "[*] Disk boyutu okunuyor..."
DISK_SIZE_GB=$(lsblk -b -dn -o SIZE "$DISK" | awk '{print int($1/1024/1024/1024)}')

if [[ "$DISK_SIZE_GB" -lt 300 ]]; then
  DATA_SIZE="130G"
elif [[ "$DISK_SIZE_GB" -lt 800 ]]; then
  DATA_SIZE="300G"
else
  DATA_SIZE="500G"
fi

echo "[*] Disk boyutu: ${DISK_SIZE_GB}G → data LV: ${DATA_SIZE}"

if lvdisplay /dev/${VG}/${LV} &>/dev/null; then
  echo "[*] data LV zaten mevcut, atlanıyor."
else
  echo "[*] data LV oluşturuluyor..."
  lvcreate -L ${DATA_SIZE} -n ${LV} ${VG}
  mkfs.ext4 /dev/${VG}/${LV}
fi

echo "[*] Mount noktası kontrol ediliyor..."
mkdir -p ${MOUNTPOINT}

UUID=$(blkid -s UUID -o value /dev/${VG}/${LV})

if grep -q "${UUID}" /etc/fstab; then
  echo "[*] fstab zaten ayarlı."
else
  echo "[*] fstab güncelleniyor..."
  echo "UUID=${UUID}  ${MOUNTPOINT}  ext4  defaults  0  2" >> /etc/fstab
fi

echo "[*] Mount ediliyor..."
mount -a

echo "[✓] /data hazır:"
df -h ${MOUNTPOINT}
