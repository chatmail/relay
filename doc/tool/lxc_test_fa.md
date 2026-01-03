# تست با LXC

برای تست تنظیمات رله در یک کانتینر محلی LXC (تست شده روی میزبان آرچ لینوکس):

### ۱. آماده‌سازی میزبان
بسته‌های مورد نیاز را نصب کنید:
```bash
sudo pacman -S lxc arch-install-scripts dnsmasq
```

### ۲. پیکربندی شبکه
اگر IPv6 در سیستم میزبان شما غیرفعال است، باید آن را برای LXC نیز غیرفعال کنید تا از بروز خطا جلوگیری شود:
فایل `/etc/default/lxc-net` را ویرایش کرده و مطمین شوید این خطوط وجود دارند:
```bash
USE_LXC_BRIDGE="true"
LXC_IPV6_ENABLE="false"
LXC_IPV6_NAT="false"
```
*نکته: اگر پورت ۵۳ اشغال است (مثلاً توسط dnscrypt-proxy)، ممکن است لازم باشد سرویس DNS خود را طوری تنظیم کنید که فقط روی `127.0.0.1` گوش دهد تا dnsmasq مربوط به LXC بتواند به بریج متصل شود.*

شبکه را راه‌اندازی کنید:
```bash
sudo systemctl enable --now lxc-net.service
```

### ۳. ساخت و آماده‌سازی کانتینر
یک کانتینر دبیان ۱۲ (bookworm) بسازید:
```bash
sudo lxc-create -n test -t download -- -d debian -r bookworm -a amd64
sudo lxc-start -n test
```

کد محلی خود را به کانتینر منتقل کنید:
```bash
sudo rsync -av --exclude=.git ./ /var/lib/lxc/test/rootfs/relay-ir/
```

### ۴. اجرای استقرار (Deployment)
به کانتینر متصل شده و استقرار را به صورت محلی اجرا کنید:
```bash
sudo lxc-attach -n test -- bash -c "cd /relay-ir && ./scripts/initenv.sh && ./scripts/cmdeploy run --ssh-host @local --skip-dns-check"
```
